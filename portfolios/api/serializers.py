"""JSON representations for portfolio ownership resources."""

from decimal import Decimal


def decimal_string(value):
    return None if value is None else format(value, "f")


def portfolio_data(portfolio):
    return {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "base_currency": portfolio.base_currency,
        "created_at": portfolio.created_at.isoformat(),
        "updated_at": portfolio.updated_at.isoformat(),
    }


def group_data(group, *, include_count=False):
    data = {
        "id": str(group.id),
        "portfolio_id": str(group.portfolio_id),
        "name": group.name,
        "mode": group.mode,
        "is_ungrouped": group.is_ungrouped,
        "provider": group.provider or None,
    }
    if include_count:
        data["holding_count"] = getattr(group, "holding_count", group.holdings.count())
    return data


def asset_type_data(asset_type):
    return {
        "id": str(asset_type.id),
        "name": asset_type.name,
        "system_category": asset_type.system_category,
        "is_system": asset_type.is_system,
        "is_active": asset_type.is_active,
    }


def asset_data(asset):
    return {
        "id": str(asset.id),
        "name": asset.name,
        "asset_type": asset_type_data(asset.asset_type),
        "native_currency": asset.native_currency or None,
        "country_code": asset.country_code or None,
        "sector": asset.sector or None,
        "industry": asset.industry or None,
        "status": asset.status,
        "metadata": asset.metadata,
        "market_linked": asset.market_linked,
        "market_data_status": asset.market_data_status,
        "market_symbol": asset.market_symbol or None,
        "market_exchange": asset.market_exchange or None,
        "market_identity": asset.market_identity,
    }


def holding_data(holding, *, valuation=None):
    if valuation is None:
        from ..services.valuation import value_holding
        valuation = value_holding(holding)
    cost_basis = (
        holding.quantity * holding.average_cost
        if holding.average_cost is not None
        else None
    )
    gain_loss = (
        valuation.value - cost_basis
        if valuation.value is not None and cost_basis is not None
        else None
    )
    return {
        "id": str(holding.id),
        "portfolio_id": str(holding.group.portfolio_id),
        "group": group_data(holding.group),
        "asset": asset_data(holding.asset),
        "status": holding.status,
        "source": holding.source,
        "quantity": decimal_string(holding.quantity),
        "average_cost": decimal_string(holding.average_cost),
        "cost_currency": holding.cost_currency or None,
        "cost_basis": decimal_string(cost_basis),
        "current_value": decimal_string(valuation.value),
        "valuation_currency": valuation.currency or None,
        "valuation_source": valuation.source,
        "valuation_stale": valuation.stale,
        "gain_loss": decimal_string(gain_loss),
        "created_at": holding.created_at.isoformat(),
        "updated_at": holding.updated_at.isoformat(),
    }


def overview_data(portfolio, overview):
    return {
        "portfolio": portfolio_data(portfolio),
        "total_value": decimal_string(overview["total_value"]),
        "valuation_currency": portfolio.base_currency,
        "holding_count": overview["holding_count"],
        "unknown_value_count": overview["unknown_value_count"],
        "currency_mismatch_count": overview["currency_mismatch_count"],
        "expected_annual_income": decimal_string(overview["expected_annual_income"]),
        "income_currency_mismatch_count": overview["income_currency_mismatch_count"],
        "current_yield": decimal_string(overview["current_yield"]),
        "yield_on_cost": decimal_string(overview["yield_on_cost"]),
        "by_group": [
            {
                **group_data(group),
                "value": decimal_string(group.value),
                "holding_count": group.holding_count,
            }
            for group in overview["groups"]
        ],
        "by_asset_type": [
            {
                **asset_type_data(asset_type),
                "value": decimal_string(asset_type.value),
                "holding_count": asset_type.holding_count,
            }
            for asset_type in overview["asset_types"]
        ],
    }
