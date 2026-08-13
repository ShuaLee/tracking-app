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
        "status": asset.status,
        "metadata": asset.metadata,
        "market_linked": asset.market_linked,
    }


def holding_data(holding):
    cost_basis = (
        holding.quantity * holding.average_cost
        if holding.average_cost is not None
        else None
    )
    gain_loss = (
        holding.manual_value - cost_basis
        if holding.manual_value is not None and cost_basis is not None
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
        "current_value": decimal_string(holding.manual_value),
        "valuation_source": "MANUAL" if holding.manual_value is not None else "UNAVAILABLE",
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

