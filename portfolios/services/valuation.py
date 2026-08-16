"""Current holding and portfolio valuation resolution."""

from dataclasses import dataclass
from decimal import Decimal

from integrations.exceptions import IntegrationError
from integrations.market_data.service import MarketDataService

from .market_data import identity_matches
from ..models import Asset, Holding


@dataclass(frozen=True, slots=True)
class Valuation:
    """Resolved current value plus source, freshness, and fallback metadata."""

    value: Decimal | None
    currency: str
    source: str
    stale: bool = False


def value_holding(holding, *, service=None):
    asset = holding.asset
    if asset.market_linked and asset.market_data_status == Asset.MarketDataStatus.LINKED:
        try:
            service = service or MarketDataService()
            profile = service.get_profile(asset.market_symbol, exchange=asset.market_exchange)
            if not identity_matches(asset, profile):
                asset.market_data_status = Asset.MarketDataStatus.NEEDS_RELINK
                asset.save(update_fields=("market_data_status", "updated_at"))
            else:
                quote = service.get_quote(asset.market_symbol, exchange=asset.market_exchange)
                return Valuation(
                    quote.price * holding.quantity,
                    quote.currency or asset.native_currency,
                    "MARKET",
                    quote.stale or profile.stale,
                )
        except IntegrationError:
            pass
    if holding.provider_value is not None:
        return Valuation(
            holding.provider_value,
            holding.cost_currency or asset.native_currency,
            "PROVIDER",
        )
    if holding.manual_value is not None:
        return Valuation(
            holding.manual_value,
            asset.portfolio.base_currency,
            "MANUAL",
        )
    return Valuation(None, asset.native_currency or holding.cost_currency, "UNAVAILABLE")
