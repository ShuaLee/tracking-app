"""JSON representations for themes, income rules, and configurable views."""

from decimal import Decimal

from .serializers import decimal_string


def theme_data(theme):
    return {
        "id": str(theme.id),
        "portfolio_id": str(theme.portfolio_id),
        "name": theme.name,
        "parent_id": str(theme.parent_id) if theme.parent_id else None,
        "target_percentage": decimal_string(theme.target_percentage),
        "color": theme.color or None,
        "created_at": theme.created_at.isoformat(),
        "updated_at": theme.updated_at.isoformat(),
    }


def assignment_data(assignment):
    return {
        "id": str(assignment.id),
        "theme_id": str(assignment.theme_id),
        "holding_id": str(assignment.holding_id),
    }


def income_rule_data(rule):
    return {
        "id": str(rule.id),
        "holding_id": str(rule.holding_id),
        "name": rule.name,
        "category": rule.category,
        "amount_per_payment": decimal_string(rule.amount_per_payment),
        "currency": rule.currency,
        "frequency": rule.frequency,
        "payments_per_year": decimal_string(rule.payments_per_year),
        "expected_annual_amount": decimal_string(rule.annual_amount),
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def block_data(block):
    return {
        "id": str(block.id),
        "view_id": str(block.view_id),
        "title": block.title,
        "data_source": block.data_source,
        "presentation": block.presentation,
        "position": block.position,
        "width": block.width,
        "configuration": block.configuration,
        "created_at": block.created_at.isoformat(),
        "updated_at": block.updated_at.isoformat(),
    }


def view_data(view, *, include_blocks=False):
    data = {
        "id": str(view.id),
        "portfolio_id": str(view.portfolio_id),
        "name": view.name,
        "description": view.description,
        "scope_mode": view.scope_mode,
        "holding_ids": [
            str(value)
            for value in view.holding_selections.values_list("holding_id", flat=True)
        ],
        "created_at": view.created_at.isoformat(),
        "updated_at": view.updated_at.isoformat(),
    }
    if include_blocks:
        data["blocks"] = [block_data(block) for block in view.blocks.all()]
    return data


def json_value(value):
    if isinstance(value, Decimal):
        return decimal_string(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, tuple):
        return [json_value(item) for item in value]
    return value


def rendered_view_data(view, rendered):
    blocks = []
    for block, result in zip(view.blocks.all(), rendered, strict=True):
        blocks.append({**block_data(block), "result": json_value(result)})
    return {**view_data(view), "blocks": blocks}
