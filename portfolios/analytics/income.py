"""Expected-income projections derived from manual rules and market dividends."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from integrations.exceptions import IntegrationError
from integrations.market_data.service import MarketDataService

from ..models import Asset, Holding, IncomeRule


@dataclass(frozen=True, slots=True)
class IncomeProjection:
    """Normalized annualized income contribution from one source."""

    name: str
    category: str
    annual_amount: Decimal
    currency: str
    source: str
    frequency: str
    stale: bool = False


def projections_for_holding(holding, *, market_service=None):
    projections = [
        IncomeProjection(
            name=rule.name,
            category=rule.category,
            annual_amount=rule.annual_amount,
            currency=rule.currency,
            source="MANUAL",
            frequency=rule.frequency,
        )
        for rule in holding.income_rules.all()
        if rule.is_active and rule.annual_amount is not None
    ]
    asset = holding.asset
    if (
        holding.status != Holding.Status.ACTIVE
        or not asset.market_linked
        or asset.market_data_status != Asset.MarketDataStatus.LINKED
    ):
        return projections
    try:
        market_service = market_service or MarketDataService()
        events = market_service.get_dividends(
            asset.market_symbol, exchange=asset.market_exchange
        )
    except IntegrationError:
        return projections
    cutoff = timezone.localdate() - timedelta(days=365)
    recent = [
        event
        for event in events
        if cutoff <= event.ex_date <= timezone.localdate()
    ]
    by_currency = {}
    stale = False
    for event in recent:
        currency = event.currency or asset.native_currency
        amount = event.adjusted_amount if event.adjusted_amount is not None else event.amount
        by_currency[currency] = by_currency.get(currency, Decimal("0")) + amount
        stale = stale or event.stale
    for currency, per_unit_amount in by_currency.items():
        projections.append(
            IncomeProjection(
                name="Trailing dividends",
                category=IncomeRule.Category.DIVIDEND,
                annual_amount=per_unit_amount * holding.quantity,
                currency=currency,
                source="MARKET",
                frequency="TRAILING_12_MONTHS",
                stale=stale,
            )
        )
    return projections


def annual_income_by_currency(holding, *, market_service=None):
    totals = {}
    for projection in projections_for_holding(holding, market_service=market_service):
        totals[projection.currency] = (
            totals.get(projection.currency, Decimal("0")) + projection.annual_amount
        )
    return totals
