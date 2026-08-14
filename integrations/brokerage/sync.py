from django.db import transaction
from django.utils import timezone

from integrations.brokerage.contracts import BrokerageCredentials
from integrations.brokerage.crypto import decrypt_secret, encrypt_secret
from integrations.brokerage.models import BrokerageConnection, BrokerageUser
from integrations.brokerage.service import BrokerageService
from integrations.exceptions import IntegrationError, ProviderResponseError
from portfolios.models import Asset, AssetType, Group, Holding


def credentials_for(user):
    identity = BrokerageUser.objects.get(user=user, provider="snaptrade")
    return BrokerageCredentials(
        user_id=identity.provider_user_id,
        user_secret=decrypt_secret(identity.encrypted_user_secret),
    )


@transaction.atomic
def ensure_brokerage_user(user, *, service=None):
    existing = BrokerageUser.objects.filter(user=user, provider="snaptrade").first()
    if existing:
        return existing
    service = service or BrokerageService()
    credentials = service.register_user(str(user.pk))
    return BrokerageUser.objects.create(
        user=user,
        provider="snaptrade",
        provider_user_id=credentials.user_id,
        encrypted_user_secret=encrypt_secret(credentials.user_secret),
    )


def create_portal(user, *, service=None, **options):
    service = service or BrokerageService()
    ensure_brokerage_user(user, service=service)
    return service.create_connection_portal(credentials_for(user), **options)


@transaction.atomic
def import_connections(user, portfolio, *, service=None):
    service = service or BrokerageService()
    ensure_brokerage_user(user, service=service)
    remote_connections = service.list_connections(credentials_for(user))
    imported = []
    for remote in remote_connections:
        if not remote.provider_connection_id:
            raise ProviderResponseError("Brokerage connection has no stable identifier.")
        existing = BrokerageConnection.objects.select_for_update().filter(
            user=user,
            provider="snaptrade",
            provider_connection_id=remote.provider_connection_id,
        ).first()
        if existing and existing.portfolio_id != portfolio.id:
            raise ProviderResponseError(
                "This brokerage connection is already assigned to another portfolio."
            )
        connection = existing or BrokerageConnection(
            user=user,
            portfolio=portfolio,
            provider="snaptrade",
            provider_connection_id=remote.provider_connection_id,
        )
        connection.name = remote.name
        connection.institution = remote.brokerage_name
        connection.brokerage_slug = remote.brokerage_slug
        connection.status = (
            BrokerageConnection.Status.DISABLED
            if remote.disabled
            else BrokerageConnection.Status.ACTIVE
        )
        connection.metadata = {
            **remote.metadata,
            "connection_type": remote.connection_type,
            "provider_created_at": (
                remote.created_at.isoformat() if remote.created_at else None
            ),
        }
        connection.full_clean()
        connection.save()
        imported.append(connection)
    return imported


def _asset_type(position):
    kind = position.security_type.lower()
    if "etf" in kind:
        name = "ETF"
    elif "fund" in kind:
        name = "Fund"
    elif "bond" in kind or "fixed" in kind:
        name = "Bond"
    elif "cash" in kind or position.metadata.get("cash_equivalent"):
        name = "Cash"
    else:
        name = "Stock"
    return AssetType.objects.get(owner__isnull=True, name=name)


def _holding_match(group, position):
    queryset = group.holdings.filter(source=Holding.Source.SYNCED)
    if position.provider_position_id:
        return queryset.filter(provider_position_id=position.provider_position_id).first()
    if position.provider_security_id:
        return queryset.filter(
            provider_position_id="", provider_security_id=position.provider_security_id
        ).first()
    return None


@transaction.atomic
def _apply_sync(connection, accounts_and_positions):
    seen_groups = set()
    created = updated = closed = 0
    now = timezone.now()
    for account, account_positions in accounts_and_positions:
        group, _ = Group.objects.update_or_create(
            portfolio=connection.portfolio,
            provider=connection.provider,
            provider_account_id=account.provider_account_id,
            defaults={
                "name": account.name,
                "mode": Group.Mode.SYNCED,
                "provider_metadata": {
                    **account.metadata,
                    "connection_id": connection.provider_connection_id,
                    "institution": account.institution,
                    "currency": account.currency,
                    "masked_number": account.masked_number,
                    "provider_value": (
                        str(account.provider_value)
                        if account.provider_value is not None
                        else None
                    ),
                    "status": account.status,
                    "account_missing": False,
                },
            },
        )
        seen_groups.add(group.pk)
        seen_holdings = set()
        for position in account_positions.positions:
            if not position.provider_position_id and not position.provider_security_id:
                raise ProviderResponseError(
                    "Brokerage position has no stable provider identifier."
                )
            holding = _holding_match(group, position)
            if holding is None:
                asset = Asset.objects.create(
                    portfolio=connection.portfolio,
                    asset_type=_asset_type(position),
                    name=position.name or position.symbol or "Brokerage position",
                    native_currency=position.currency,
                    metadata={"source": connection.provider},
                )
                holding = Holding(group=group, asset=asset, source=Holding.Source.SYNCED)
                created += 1
            else:
                updated += 1
            holding.status = Holding.Status.ACTIVE
            holding.quantity = position.quantity
            holding.average_cost = position.average_cost
            holding.cost_currency = position.currency
            holding.provider_value = position.provider_value
            holding.provider_value_as_of = now
            holding.provider_position_id = position.provider_position_id or ""
            holding.provider_security_id = position.provider_security_id or ""
            holding.provider_metadata = {
                **position.metadata,
                "symbol": position.symbol,
                "raw_symbol": position.raw_symbol,
                "exchange": position.exchange,
                "security_type": position.security_type,
                "provider_price": (
                    str(position.provider_price)
                    if position.provider_price is not None
                    else None
                ),
                "data_freshness": account_positions.data_freshness,
            }
            holding.full_clean()
            holding.save()
            seen_holdings.add(holding.pk)
        missing = group.holdings.filter(source=Holding.Source.SYNCED).exclude(pk__in=seen_holdings)
        closed += missing.exclude(status=Holding.Status.CLOSED).count()
        missing.update(status=Holding.Status.CLOSED)

    stale_groups = Group.objects.filter(
        portfolio=connection.portfolio,
        mode=Group.Mode.SYNCED,
        provider=connection.provider,
        provider_metadata__connection_id=connection.provider_connection_id,
    ).exclude(pk__in=seen_groups)
    for group in stale_groups:
        metadata = dict(group.provider_metadata)
        metadata["account_missing"] = True
        group.provider_metadata = metadata
        group.save(update_fields=("provider_metadata", "updated_at"))
        missing = group.holdings.filter(source=Holding.Source.SYNCED)
        closed += missing.exclude(status=Holding.Status.CLOSED).count()
        missing.update(status=Holding.Status.CLOSED)
    connection.status = BrokerageConnection.Status.ACTIVE
    connection.last_synced_at = now
    connection.last_error_code = ""
    connection.last_error_at = None
    connection.save(update_fields=(
        "status", "last_synced_at", "last_error_code", "last_error_at", "updated_at"
    ))
    return {"created": created, "updated": updated, "closed": closed}


def sync_connection(connection, *, service=None):
    if connection.status != BrokerageConnection.Status.ACTIVE:
        raise ValueError("Only an active brokerage connection can be synced.")
    service = service or BrokerageService()
    try:
        credentials = credentials_for(connection.user)
        accounts = [
            account for account in service.list_accounts(credentials)
            if account.provider_connection_id == connection.provider_connection_id
        ]
        if any(not account.provider_account_id for account in accounts):
            raise ProviderResponseError(
                "Brokerage account has no stable provider identifier."
            )
        results = [
            (account, service.list_positions(credentials, account.provider_account_id))
            for account in accounts
        ]
    except IntegrationError as exc:
        connection.last_error_code = exc.code
        connection.last_error_at = timezone.now()
        connection.save(update_fields=("last_error_code", "last_error_at", "updated_at"))
        raise
    return _apply_sync(connection, results)


def refresh_connection(connection, *, service=None):
    service = service or BrokerageService()
    return service.refresh_connection(
        credentials_for(connection.user), connection.provider_connection_id
    )


@transaction.atomic
def disconnect_connection(connection, *, service=None):
    service = service or BrokerageService()
    service.disconnect(credentials_for(connection.user), connection.provider_connection_id)
    connection.status = BrokerageConnection.Status.DISCONNECTED
    connection.save(update_fields=("status", "updated_at"))
    for group in Group.objects.filter(
        portfolio=connection.portfolio,
        provider=connection.provider,
        provider_metadata__connection_id=connection.provider_connection_id,
    ):
        metadata = dict(group.provider_metadata)
        metadata["disconnected"] = True
        group.provider_metadata = metadata
        group.save(update_fields=("provider_metadata", "updated_at"))
    return connection
