from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def integration_deployment_checks(app_configs, **kwargs):
    messages = []
    redis_url = getattr(settings, "REDIS_URL", "")
    market_data = getattr(settings, "MARKET_DATA", {})
    brokerage = getattr(settings, "BROKERAGE", {})

    if not redis_url:
        messages.append(
            Error(
                "Production market-data caching requires REDIS_URL.",
                hint="Configure a dedicated Redis database over a protected network.",
                id="integrations.E001",
            )
        )
    elif urlparse(redis_url).scheme not in {"redis", "rediss"}:
        messages.append(
            Error(
                "REDIS_URL must use the redis:// or rediss:// scheme.",
                id="integrations.E002",
            )
        )

    if not market_data.get("FMP_API_KEY"):
        messages.append(
            Error(
                "FMP_API_KEY is required for the production market-data adapter.",
                id="integrations.E003",
            )
        )
    if not str(market_data.get("FMP_BASE_URL", "")).startswith("https://"):
        messages.append(
            Error(
                "FMP_BASE_URL must use HTTPS in production.",
                id="integrations.E004",
            )
        )
    if not brokerage.get("SNAPTRADE_CLIENT_ID") or not brokerage.get(
        "SNAPTRADE_CONSUMER_KEY"
    ):
        messages.append(
            Error(
                "SnapTrade partner credentials are required in production.",
                id="integrations.E005",
            )
        )
    if not getattr(settings, "BROKERAGE_CREDENTIAL_ENCRYPTION_KEY", ""):
        messages.append(
            Error(
                "BROKERAGE_CREDENTIAL_ENCRYPTION_KEY is required in production.",
                hint="Generate a Fernet key and store it in the deployment secret manager.",
                id="integrations.E006",
            )
        )

    ttls = market_data.get("TTLS", {})
    for fresh, stale in (
        ("SEARCH", "SEARCH_STALE"),
        ("QUOTE", "QUOTE_STALE"),
        ("PROFILE", "PROFILE_STALE"),
        ("DIVIDENDS", "DIVIDENDS_STALE"),
    ):
        if ttls.get(fresh, 0) <= 0 or ttls.get(stale, 0) < ttls.get(fresh, 0):
            messages.append(
                Warning(
                    f"Market-data TTLs {fresh}/{stale} are inconsistent.",
                    hint="Use a positive fresh TTL and a stale TTL at least as long.",
                    id="integrations.W001",
                )
            )
            break
    return messages
