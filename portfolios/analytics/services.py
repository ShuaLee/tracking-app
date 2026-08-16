"""Application services for themes, income rules, and configurable views."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max

from subscriptions.entitlements import has

from ..exceptions import PortfolioDomainError, ProtectedOperationError
from ..models import (
    Holding,
    IncomeRule,
    PortfolioView,
    Theme,
    ThemeAssignment,
    ViewBlock,
    ViewHoldingSelection,
)
from ..services.holdings import _decimal, _validate


def _text(value):
    return "" if value is None else str(value).strip()


def require_advanced_sheets(user):
    if not has(user, "advanced_sheets"):
        raise PortfolioDomainError(
            "Your plan does not include configurable portfolio views.",
            code="entitlement_required",
        )


def _save_unique(instance, message, field="name"):
    _validate(instance)
    try:
        instance.save()
    except IntegrityError as exc:
        raise PortfolioDomainError(
            message, fields={field: [message]}
        ) from exc
    return instance


@transaction.atomic
def create_theme(*, portfolio, name, parent=None, target_percentage=None, color=""):
    require_advanced_sheets(portfolio.owner)
    theme = Theme(
        portfolio=portfolio,
        parent=parent,
        name=_text(name),
        target_percentage=_decimal(target_percentage, "target_percentage"),
        color=_text(color),
    )
    return _save_unique(theme, "Theme names must be unique within a portfolio.")


@transaction.atomic
def update_theme(theme, **changes):
    require_advanced_sheets(theme.portfolio.owner)
    for field in ("name", "parent", "color"):
        if field in changes:
            value = changes[field]
            if field in ("name", "color"):
                value = _text(value)
            setattr(theme, field, value)
    if "target_percentage" in changes:
        theme.target_percentage = _decimal(
            changes["target_percentage"], "target_percentage"
        )
    return _save_unique(theme, "Theme names must be unique within a portfolio.")


@transaction.atomic
def delete_theme(theme):
    require_advanced_sheets(theme.portfolio.owner)
    if theme.children.exists():
        raise ProtectedOperationError("A theme with subthemes cannot be deleted.")
    theme.delete()


@transaction.atomic
def assign_theme(*, theme, holding):
    require_advanced_sheets(theme.portfolio.owner)
    original_holding = holding
    holding = Holding.objects.select_for_update().select_related(
        "group__portfolio__owner"
    ).get(pk=holding.pk)
    assignment = ThemeAssignment.objects.filter(holding=holding).first()
    if assignment is None:
        assignment = ThemeAssignment(theme=theme, holding=holding)
    else:
        assignment.theme = theme
    _validate(assignment)
    assignment.save()
    original_holding._state.fields_cache.pop("theme_assignment", None)
    return assignment


@transaction.atomic
def unassign_theme(*, holding):
    require_advanced_sheets(holding.group.portfolio.owner)
    ThemeAssignment.objects.filter(holding=holding).delete()
    holding._state.fields_cache.pop("theme_assignment", None)


@transaction.atomic
def create_income_rule(
    *, holding, name, category, amount_per_payment, currency,
    frequency, payments_per_year=None, is_active=True
):
    require_advanced_sheets(holding.group.portfolio.owner)
    if not isinstance(is_active, bool):
        raise PortfolioDomainError(
            "Income rule is invalid.", fields={"is_active": ["Enter true or false."]}
        )
    rule = IncomeRule(
        holding=holding,
        name=_text(name),
        category=category,
        amount_per_payment=_decimal(
            amount_per_payment, "amount_per_payment", required=True
        ),
        currency=_text(currency).upper(),
        frequency=frequency,
        payments_per_year=_decimal(payments_per_year, "payments_per_year"),
        is_active=bool(is_active),
    )
    _validate(rule)
    rule.save()
    return rule


@transaction.atomic
def update_income_rule(rule, **changes):
    require_advanced_sheets(rule.holding.group.portfolio.owner)
    if "is_active" in changes and not isinstance(changes["is_active"], bool):
        raise PortfolioDomainError(
            "Income rule is invalid.", fields={"is_active": ["Enter true or false."]}
        )
    for field in ("name", "category", "currency", "frequency", "is_active"):
        if field in changes:
            value = changes[field]
            if field in ("name", "currency"):
                value = _text(value)
            setattr(rule, field, value)
    for field in ("amount_per_payment", "payments_per_year"):
        if field in changes:
            setattr(
                rule,
                field,
                _decimal(changes[field], field, required=(field == "amount_per_payment")),
            )
    _validate(rule)
    rule.save()
    return rule


@transaction.atomic
def delete_income_rule(rule):
    require_advanced_sheets(rule.holding.group.portfolio.owner)
    rule.delete()


def _set_view_scope(view, *, scope_mode, holding_ids=None):
    if scope_mode not in PortfolioView.ScopeMode.values:
        raise PortfolioDomainError(
            "View scope is invalid.",
            fields={"scope_mode": ["Choose ALL or SELECTED."]},
        )
    if holding_ids is None:
        holding_ids = []
    if not isinstance(holding_ids, list):
        raise PortfolioDomainError(
            "View scope is invalid.",
            fields={"holding_ids": ["Enter a list of holding IDs."]},
        )
    normalized_ids = list(dict.fromkeys(str(value) for value in holding_ids))
    if scope_mode == PortfolioView.ScopeMode.ALL and normalized_ids:
        raise PortfolioDomainError(
            "View scope is invalid.",
            fields={"holding_ids": ["ALL scope cannot contain selected holdings."]},
        )
    try:
        holdings = list(
            Holding.objects.filter(
                group__portfolio=view.portfolio, pk__in=normalized_ids
            )
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise PortfolioDomainError(
            "View scope is invalid.",
            fields={"holding_ids": ["One or more holding IDs are invalid."]},
        ) from exc
    if len(holdings) != len(normalized_ids):
        raise PortfolioDomainError(
            "View scope is invalid.",
            fields={"holding_ids": ["One or more holdings are unavailable."]},
        )
    view.scope_mode = scope_mode
    view.save(update_fields=("scope_mode", "updated_at"))
    view.holding_selections.all().delete()
    ViewHoldingSelection.objects.bulk_create(
        [ViewHoldingSelection(view=view, holding=holding) for holding in holdings]
    )
    return view


@transaction.atomic
def create_view(
    *, portfolio, name, description="", scope_mode=PortfolioView.ScopeMode.ALL,
    holding_ids=None
):
    require_advanced_sheets(portfolio.owner)
    view = PortfolioView(
        portfolio=portfolio,
        name=_text(name),
        description=_text(description),
    )
    view = _save_unique(view, "View names must be unique within a portfolio.")
    return _set_view_scope(
        view, scope_mode=scope_mode, holding_ids=holding_ids
    )


@transaction.atomic
def create_view_from_template(
    *, portfolio, name, description="", template=None, source_view=None,
    scope_mode=None, holding_ids=None
):
    if template and source_view is not None:
        raise PortfolioDomainError(
            "View source is invalid.",
            fields={"source_view_id": ["Choose a template or an existing View, not both."]},
        )
    if source_view is not None and source_view.portfolio_id != portfolio.id:
        raise PortfolioDomainError(
            "View source is invalid.",
            fields={"source_view_id": ["Source View belongs to another portfolio."]},
        )
    if scope_mode is None:
        scope_mode = (
            source_view.scope_mode
            if source_view is not None
            else PortfolioView.ScopeMode.SELECTED
            if holding_ids is not None
            else PortfolioView.ScopeMode.ALL
        )
    if holding_ids is None and source_view is not None:
        holding_ids = (
            []
            if scope_mode == PortfolioView.ScopeMode.ALL
            else list(
                source_view.holding_selections.values_list("holding_id", flat=True)
            )
        )
    view = create_view(
        portfolio=portfolio,
        name=name,
        description=description or (source_view.description if source_view else ""),
        scope_mode=scope_mode,
        holding_ids=holding_ids,
    )
    if source_view is not None:
        for block in source_view.blocks.all():
            create_block(
                view=view,
                title=block.title,
                data_source=block.data_source,
                presentation=block.presentation,
                position=block.position,
                width=block.width,
                configuration=block.configuration,
            )
        return view
    if not template:
        return view
    from .templates import VIEW_TEMPLATES

    specification = VIEW_TEMPLATES.get(template)
    if specification is None:
        raise PortfolioDomainError(
            "View template is invalid.", fields={"template": ["Unknown template."]}
        )
    if not description:
        view.description = specification["description"]
        view.save(update_fields=("description", "updated_at"))
    for position, block in enumerate(specification["blocks"]):
        create_block(view=view, position=position, **block)
    return view


@transaction.atomic
def update_view(view, **changes):
    require_advanced_sheets(view.portfolio.owner)
    for field in ("name", "description"):
        if field in changes:
            setattr(view, field, _text(changes[field]))
    view = _save_unique(view, "View names must be unique within a portfolio.")
    if "holding_ids" in changes or "scope_mode" in changes:
        holding_ids = changes.get("holding_ids")
        scope_mode = changes.get("scope_mode")
        if scope_mode is None:
            scope_mode = (
                PortfolioView.ScopeMode.SELECTED
                if holding_ids is not None
                else view.scope_mode
            )
        if holding_ids is None and scope_mode == PortfolioView.ScopeMode.SELECTED:
            holding_ids = list(
                view.holding_selections.values_list("holding_id", flat=True)
            )
        _set_view_scope(view, scope_mode=scope_mode, holding_ids=holding_ids)
    return view


@transaction.atomic
def delete_view(view):
    require_advanced_sheets(view.portfolio.owner)
    view.delete()


@transaction.atomic
def update_asset_classification(holding, **changes):
    require_advanced_sheets(holding.group.portfolio.owner)
    asset = holding.asset.__class__.objects.select_for_update().get(
        pk=holding.asset_id
    )
    for field in ("country_code", "sector", "industry"):
        if field in changes:
            value = _text(changes[field])
            if field == "country_code":
                value = value.upper()
            setattr(asset, field, value)
    _validate(asset)
    asset.save()
    holding.asset = asset
    return asset


def _shift_for_insert(view, position):
    blocks = list(view.blocks.select_for_update().filter(position__gte=position).order_by("-position"))
    for block in blocks:
        block.position += 1
        block.save(update_fields=("position", "updated_at"))


@transaction.atomic
def create_block(
    *, view, data_source, presentation, title="", position=None, width=12,
    configuration=None
):
    require_advanced_sheets(view.portfolio.owner)
    view = PortfolioView.objects.select_for_update().select_related(
        "portfolio__owner"
    ).get(pk=view.pk)
    current_max = view.blocks.aggregate(value=Max("position"))["value"]
    position = current_max + 1 if position is None and current_max is not None else position
    position = 0 if position is None else int(position)
    if position < 0:
        raise PortfolioDomainError(
            "View block is invalid.", fields={"position": ["Position cannot be negative."]}
        )
    position = min(position, view.blocks.count())
    _shift_for_insert(view, position)
    block = ViewBlock(
        view=view,
        data_source=data_source,
        presentation=presentation,
        title=_text(title),
        position=position,
        width=width,
        configuration={} if configuration is None else configuration,
    )
    _validate(block)
    block.save()
    return block


def _move_block(block, target):
    target = int(target)
    if target < 0:
        raise PortfolioDomainError(
            "View block is invalid.", fields={"position": ["Position cannot be negative."]}
        )
    siblings = list(block.view.blocks.select_for_update().exclude(pk=block.pk))
    maximum = len(siblings)
    target = min(target, maximum)
    old = block.position
    sentinel = (max([item.position for item in siblings] + [old]) + 1000)
    block.position = sentinel
    block.save(update_fields=("position", "updated_at"))
    if target < old:
        affected = sorted(
            [item for item in siblings if target <= item.position < old],
            key=lambda item: item.position,
            reverse=True,
        )
        for item in affected:
            item.position += 1
            item.save(update_fields=("position", "updated_at"))
    elif target > old:
        affected = sorted(
            [item for item in siblings if old < item.position <= target],
            key=lambda item: item.position,
        )
        for item in affected:
            item.position -= 1
            item.save(update_fields=("position", "updated_at"))
    block.position = target


@transaction.atomic
def update_block(block, **changes):
    require_advanced_sheets(block.view.portfolio.owner)
    PortfolioView.objects.select_for_update().get(pk=block.view_id)
    block = ViewBlock.objects.select_for_update().select_related(
        "view__portfolio__owner"
    ).get(pk=block.pk)
    if "position" in changes and int(changes["position"]) != block.position:
        _move_block(block, changes.pop("position"))
    for field in ("data_source", "presentation", "title", "width", "configuration"):
        if field in changes:
            value = changes[field]
            if field == "title":
                value = _text(value)
            setattr(block, field, value)
    _validate(block)
    block.save()
    return block


@transaction.atomic
def delete_block(block):
    require_advanced_sheets(block.view.portfolio.owner)
    PortfolioView.objects.select_for_update().get(pk=block.view_id)
    block = ViewBlock.objects.select_for_update().select_related("view").get(pk=block.pk)
    position = block.position
    view = block.view
    block.delete()
    for sibling in view.blocks.select_for_update().filter(position__gt=position).order_by("position"):
        sibling.position -= 1
        sibling.save(update_fields=("position", "updated_at"))
