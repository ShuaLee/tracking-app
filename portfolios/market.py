from django.db import transaction

from integrations.market_data.service import MarketDataService
from subscriptions.entitlements import limit

from .exceptions import EntitlementLimitError, PortfolioDomainError, ProtectedOperationError
from .models import Asset, AssetType, Group, Holding
from .services import _decimal, _validate


def identity_snapshot(profile):
    return {
        **profile.identity,
        "symbol": profile.symbol.upper(),
        "exchange": profile.exchange.upper(),
        "name": profile.name,
        "currency": profile.currency.upper(),
    }


def identity_matches(asset, profile):
    saved = asset.market_identity or {}
    stable_keys = ("isin", "cusip", "cik")
    comparable = [key for key in stable_keys if saved.get(key) and profile.identity.get(key)]
    if comparable:
        return all(str(saved[key]) == str(profile.identity[key]) for key in comparable)
    if any(saved.get(key) for key in stable_keys):
        return False
    return (
        saved.get("symbol", asset.market_symbol).upper() == profile.symbol.upper()
        and saved.get("exchange", asset.market_exchange).upper()
        == profile.exchange.upper()
    )


def _type_for(profile):
    kind = profile.security_type.lower()
    if "etf" in kind:
        name = "ETF"
    elif "fund" in kind:
        name = "Fund"
    elif "bond" in kind:
        name = "Bond"
    else:
        name = "Stock"
    return AssetType.objects.get(owner__isnull=True, name=name)


@transaction.atomic
def create_market_holding(
    *, portfolio, symbol, exchange="", group=None, quantity=1,
    average_cost=None, cost_currency="", service=None
):
    service = service or MarketDataService()
    portfolio.owner.__class__.objects.select_for_update().get(pk=portfolio.owner_id)
    maximum = limit(portfolio.owner, "holdings")
    current = Holding.objects.filter(group__portfolio__owner=portfolio.owner).count()
    if maximum is not None and current >= maximum:
        raise EntitlementLimitError(
            f"Your plan allows at most {maximum} holding(s).", resource="holdings"
        )
    profile = service.get_profile(symbol, exchange=exchange)
    group = group or portfolio.groups.select_for_update().get(is_ungrouped=True)
    if group.portfolio_id != portfolio.id:
        raise PortfolioDomainError(
            "Portfolio data is invalid.",
            fields={"group_id": ["Group belongs to another portfolio."]},
        )
    if group.mode == Group.Mode.SYNCED:
        raise ProtectedOperationError("Manual holdings cannot be added to a synced group.")
    asset = Asset(
        portfolio=portfolio,
        asset_type=_type_for(profile),
        name=profile.name,
        native_currency=profile.currency,
        market_linked=True,
        market_data_status=Asset.MarketDataStatus.LINKED,
        market_symbol=profile.symbol,
        market_exchange=profile.exchange,
        market_identity=identity_snapshot(profile),
    )
    _validate(asset)
    asset.save()
    holding = Holding(
        group=group,
        asset=asset,
        source=Holding.Source.MANUAL,
        quantity=_decimal(quantity, "quantity", required=True),
        average_cost=_decimal(average_cost, "average_cost"),
        cost_currency=str(cost_currency or profile.currency).strip().upper(),
    )
    _validate(holding)
    holding.save()
    return holding


@transaction.atomic
def relink_market_holding(*, holding, symbol, exchange="", service=None):
    if holding.source != holding.Source.MANUAL:
        raise ProtectedOperationError("Provider-controlled holdings cannot be relinked manually.")
    service = service or MarketDataService()
    profile = service.get_profile(symbol, exchange=exchange)
    asset = holding.asset
    asset.name = profile.name
    asset.asset_type = _type_for(profile)
    asset.native_currency = profile.currency
    asset.market_linked = True
    asset.market_data_status = Asset.MarketDataStatus.LINKED
    asset.market_symbol = profile.symbol
    asset.market_exchange = profile.exchange
    asset.market_identity = identity_snapshot(profile)
    _validate(asset)
    asset.save()
    return holding
