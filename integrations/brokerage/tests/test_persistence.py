from decimal import Decimal
from unittest.mock import Mock

from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from integrations.brokerage.contracts import (
    AccountPositions,
    BrokerageCredentials,
    NormalizedBrokerageAccount,
    NormalizedPosition,
)
from integrations.brokerage.crypto import decrypt_secret, encrypt_secret
from integrations.brokerage.models import BrokerageConnection, BrokerageUser
from integrations.brokerage.sync import ensure_brokerage_user, sync_connection
from integrations.exceptions import ProviderUnavailableError
from portfolios.models import Group, Holding
from portfolios.tests.factories import portfolio, user
from subscriptions.models import Subscription


@override_settings(
    BROKERAGE_CREDENTIAL_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii")
)
class BrokeragePersistenceTests(TestCase):
    def setUp(self):
        self.user = user(plan=Subscription.Plan.PRO)
        self.portfolio = portfolio(self.user)

    def test_provider_secret_is_encrypted_at_rest(self):
        service = Mock()
        service.register_user.return_value = BrokerageCredentials("provider-user", "plain-secret")

        identity = ensure_brokerage_user(self.user, service=service)

        self.assertNotIn("plain-secret", identity.encrypted_user_secret)
        self.assertEqual(decrypt_secret(identity.encrypted_user_secret), "plain-secret")
        self.assertEqual(ensure_brokerage_user(self.user, service=service), identity)
        service.register_user.assert_called_once()

    def test_connection_rejects_another_users_portfolio(self):
        other = user("other@example.com", plan=Subscription.Plan.PRO)
        connection = BrokerageConnection(
            user=other,
            portfolio=self.portfolio,
            provider_connection_id="connection-1",
            name="Broker",
        )
        with self.assertRaises(ValidationError):
            connection.full_clean()

    def test_sync_is_idempotent_and_closes_only_after_successful_empty_snapshot(self):
        BrokerageUser.objects.create(
            user=self.user,
            provider_user_id="provider-user",
            encrypted_user_secret=encrypt_secret("secret"),
        )
        connection = BrokerageConnection.objects.create(
            user=self.user,
            portfolio=self.portfolio,
            provider_connection_id="connection-1",
            name="Broker",
        )
        account = NormalizedBrokerageAccount(
            provider_account_id="account-1",
            provider_connection_id="connection-1",
            name="TFSA",
            institution="Broker",
            currency="CAD",
        )
        position = NormalizedPosition(
            provider_position_id=None,
            provider_security_id="security-1",
            symbol="SHOP",
            raw_symbol="SHOP",
            name="Shopify",
            quantity=Decimal("2"),
            average_cost=Decimal("80"),
            currency="CAD",
            provider_price=Decimal("100"),
            provider_value=Decimal("200"),
        )
        service = Mock()
        service.list_accounts.return_value = [account]
        service.list_positions.return_value = AccountPositions("account-1", (position,))

        first = sync_connection(connection, service=service)
        second = sync_connection(connection, service=service)

        self.assertEqual(first, {"created": 1, "updated": 0, "closed": 0})
        self.assertEqual(second, {"created": 0, "updated": 1, "closed": 0})
        self.assertEqual(Holding.objects.count(), 1)
        holding = Holding.objects.get()
        self.assertEqual(holding.provider_value, Decimal("200"))
        self.assertEqual(holding.group.mode, Group.Mode.SYNCED)

        service.list_accounts.side_effect = ProviderUnavailableError("offline")
        with self.assertRaises(ProviderUnavailableError):
            sync_connection(connection, service=service)
        holding.refresh_from_db()
        self.assertEqual(holding.status, Holding.Status.ACTIVE)

        service.list_accounts.side_effect = None
        service.list_positions.return_value = AccountPositions("account-1", ())
        result = sync_connection(connection, service=service)
        holding.refresh_from_db()
        self.assertEqual(result["closed"], 1)
        self.assertEqual(holding.status, Holding.Status.CLOSED)
