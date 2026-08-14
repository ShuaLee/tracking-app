from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from subscriptions.entitlements import limit

from .exceptions import EntitlementLimitError, PortfolioDomainError, ProtectedOperationError
from .models import Asset, AssetType, Group, Holding, Portfolio


def _validation_error(exc):
    fields = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
    return PortfolioDomainError("Portfolio data is invalid.", fields=fields)


def _decimal(value, field, *, required=False):
    if value in (None, ""):
        if required:
            raise PortfolioDomainError(
                "Portfolio data is invalid.", fields={field: ["This field is required."]}
            )
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PortfolioDomainError(
            "Portfolio data is invalid.", fields={field: ["Enter a valid decimal number."]}
        ) from exc


def _validate(instance):
    try:
        instance.full_clean()
    except ValidationError as exc:
        raise _validation_error(exc) from exc


@transaction.atomic
def create_portfolio(*, owner, name, base_currency="USD"):
    owner.__class__.objects.select_for_update().get(pk=owner.pk)
    maximum = limit(owner, "portfolios")
    current = Portfolio.objects.filter(owner=owner).count()
    if maximum is not None and current >= maximum:
        raise EntitlementLimitError(
            f"Your plan allows at most {maximum} portfolio(s).",
            resource="portfolios",
        )
    portfolio = Portfolio(
        owner=owner,
        name=str(name).strip(),
        base_currency=str(base_currency).strip().upper(),
    )
    _validate(portfolio)
    portfolio.save()
    Group.objects.create(
        portfolio=portfolio,
        name="Ungrouped",
        mode=Group.Mode.SYSTEM,
        is_ungrouped=True,
    )
    return portfolio


@transaction.atomic
def update_portfolio(*, portfolio, name=None, base_currency=None):
    if name is not None:
        portfolio.name = str(name).strip()
    if base_currency is not None:
        portfolio.base_currency = str(base_currency).strip().upper()
    _validate(portfolio)
    portfolio.save()
    return portfolio


@transaction.atomic
def delete_portfolio(*, portfolio):
    Holding.objects.filter(group__portfolio=portfolio).delete()
    Asset.objects.filter(portfolio=portfolio).delete()
    Group.objects.filter(portfolio=portfolio).delete()
    portfolio.delete()


@transaction.atomic
def create_manual_group(*, portfolio, name):
    group = Group(portfolio=portfolio, name=str(name).strip(), mode=Group.Mode.MANUAL)
    _validate(group)
    group.save()
    return group


@transaction.atomic
def update_manual_group(*, group, name):
    if group.mode != Group.Mode.MANUAL:
        raise ProtectedOperationError("Only manual groups can be renamed.")
    group.name = str(name).strip()
    _validate(group)
    group.save()
    return group


@transaction.atomic
def delete_manual_group(*, group):
    if group.mode != Group.Mode.MANUAL:
        raise ProtectedOperationError("System and synced groups cannot be deleted manually.")
    ungrouped = group.portfolio.groups.select_for_update().get(is_ungrouped=True)
    group.holdings.filter(source=Holding.Source.MANUAL).update(group=ungrouped)
    if group.holdings.exists():
        raise ProtectedOperationError("A group containing synced holdings cannot be deleted.")
    group.delete()


@transaction.atomic
def create_custom_asset_type(*, owner, name, system_category):
    asset_type = AssetType(
        owner=owner,
        name=str(name).strip(),
        system_category=system_category,
    )
    _validate(asset_type)
    try:
        asset_type.save()
    except IntegrityError as exc:
        raise PortfolioDomainError(
            "Asset type already exists.", fields={"name": ["Asset type names must be unique."]}
        ) from exc
    return asset_type


@transaction.atomic
def update_custom_asset_type(*, asset_type, name=None, system_category=None):
    if asset_type.is_system:
        raise ProtectedOperationError("Built-in asset types cannot be changed.")
    if name is not None:
        asset_type.name = str(name).strip()
    if system_category is not None:
        asset_type.system_category = system_category
    _validate(asset_type)
    try:
        asset_type.save()
    except IntegrityError as exc:
        raise PortfolioDomainError(
            "Asset type already exists.", fields={"name": ["Asset type names must be unique."]}
        ) from exc
    return asset_type


@transaction.atomic
def delete_custom_asset_type(*, asset_type):
    if asset_type.is_system:
        raise ProtectedOperationError("Built-in asset types cannot be deleted.")
    if asset_type.assets.exists():
        raise ProtectedOperationError("Asset types in use must be reassigned before deletion.")
    asset_type.delete()


@transaction.atomic
def create_manual_holding(
    *,
    portfolio,
    asset_type,
    name,
    group=None,
    native_currency="",
    metadata=None,
    quantity=1,
    average_cost=None,
    cost_currency="",
    manual_value=None,
):
    portfolio.owner.__class__.objects.select_for_update().get(pk=portfolio.owner_id)
    maximum = limit(portfolio.owner, "holdings")
    current = Holding.objects.filter(group__portfolio__owner=portfolio.owner).count()
    if maximum is not None and current >= maximum:
        raise EntitlementLimitError(
            f"Your plan allows at most {maximum} holding(s).",
            resource="holdings",
        )
    group = group or portfolio.groups.select_for_update().get(is_ungrouped=True)
    if group.portfolio_id != portfolio.id:
        raise PortfolioDomainError(
            "Portfolio data is invalid.", fields={"group_id": ["Group belongs to another portfolio."]}
        )
    if group.mode == Group.Mode.SYNCED:
        raise ProtectedOperationError("Manual holdings cannot be added to a synced group.")
    if asset_type.owner_id not in (None, portfolio.owner_id):
        raise PortfolioDomainError(
            "Portfolio data is invalid.",
            fields={"asset_type_id": ["Asset type is not available to this owner."]},
        )
    quantity = _decimal(quantity, "quantity", required=True)
    average_cost = _decimal(average_cost, "average_cost")
    manual_value = _decimal(manual_value, "manual_value")
    asset = Asset(
        portfolio=portfolio,
        asset_type=asset_type,
        name=str(name).strip(),
        native_currency=str(native_currency).strip().upper(),
        metadata=metadata or {},
    )
    _validate(asset)
    asset.save()
    holding = Holding(
        group=group,
        asset=asset,
        source=Holding.Source.MANUAL,
        quantity=quantity,
        average_cost=average_cost,
        cost_currency=str(cost_currency).strip().upper(),
        manual_value=manual_value,
    )
    _validate(holding)
    holding.save()
    return holding


@transaction.atomic
def update_manual_holding(*, holding, **changes):
    if holding.source != Holding.Source.MANUAL:
        raise ProtectedOperationError("Provider-controlled holdings cannot be changed manually.")
    if holding.asset.market_linked and any(
        field in changes for field in ("name", "native_currency", "asset_type")
    ):
        raise ProtectedOperationError(
            "Market-linked identity must be changed through the relink operation."
        )
    if "group" in changes:
        group = changes["group"]
        if group.portfolio_id != holding.asset.portfolio_id:
            raise PortfolioDomainError(
                "Portfolio data is invalid.", fields={"group_id": ["Group belongs to another portfolio."]}
            )
        if group.mode == Group.Mode.SYNCED:
            raise ProtectedOperationError("Manual holdings cannot be moved into a synced group.")
        holding.group = group
    for field in ("quantity", "average_cost", "manual_value"):
        if field in changes:
            setattr(
                holding,
                field,
                _decimal(changes[field], field, required=(field == "quantity")),
            )
    if "cost_currency" in changes:
        holding.cost_currency = str(changes["cost_currency"]).strip().upper()
    asset = holding.asset
    for field in ("name", "native_currency", "metadata"):
        if field in changes:
            value = changes[field]
            if field in ("name", "native_currency"):
                value = str(value).strip()
            setattr(asset, field, value)
    if "asset_status" in changes:
        asset.status = changes["asset_status"]
    if "holding_status" in changes:
        holding.status = changes["holding_status"]
    if "asset_type" in changes:
        asset_type = changes["asset_type"]
        if asset_type.owner_id not in (None, asset.portfolio.owner_id):
            raise PortfolioDomainError(
                "Portfolio data is invalid.",
                fields={"asset_type_id": ["Asset type is not available to this owner."]},
            )
        asset.asset_type = asset_type
    _validate(asset)
    asset.save()
    _validate(holding)
    holding.save()
    return holding


@transaction.atomic
def delete_manual_holding(*, holding):
    if holding.source != Holding.Source.MANUAL:
        raise ProtectedOperationError("Provider-controlled holdings cannot be deleted manually.")
    asset = holding.asset
    holding.delete()
    if not asset.holdings.exists():
        asset.delete()


def portfolio_overview(portfolio):
    active = list(Holding.objects.filter(
        group__portfolio=portfolio,
        status=Holding.Status.ACTIVE,
    ).select_related("group", "asset", "asset__asset_type"))
    from .valuation import value_holding
    valuations = {holding.pk: value_holding(holding) for holding in active}
    known = [
        value for value in valuations.values()
        if value.value is not None and value.currency == portfolio.base_currency
    ]
    currency_mismatches = [
        value for value in valuations.values()
        if value.value is not None and value.currency != portfolio.base_currency
    ]
    total = sum((value.value for value in known), Decimal("0")).normalize()
    group_rows = []
    for group in portfolio.groups.all():
        items = [holding for holding in active if holding.group_id == group.pk]
        group.value = sum(
            (
                valuations[item.pk].value for item in items
                if valuations[item.pk].value is not None
                and valuations[item.pk].currency == portfolio.base_currency
            ),
            Decimal("0"),
        )
        group.holding_count = len(items)
        group_rows.append(group)
    type_rows = []
    for asset_type in AssetType.objects.filter(assets__portfolio=portfolio).distinct():
        items = [holding for holding in active if holding.asset.asset_type_id == asset_type.pk]
        asset_type.value = sum(
            (
                valuations[item.pk].value for item in items
                if valuations[item.pk].value is not None
                and valuations[item.pk].currency == portfolio.base_currency
            ),
            Decimal("0"),
        )
        asset_type.holding_count = len(items)
        type_rows.append(asset_type)
    return {
        "total_value": total,
        "unknown_value_count": len(active) - len(known),
        "currency_mismatch_count": len(currency_mismatches),
        "holding_count": len(active),
        "groups": group_rows,
        "asset_types": type_rows,
    }
