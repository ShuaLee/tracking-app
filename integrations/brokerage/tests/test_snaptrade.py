from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase
from snaptrade_client import SnapTrade
from snaptrade_client.exceptions import ApiException

from integrations.brokerage.contracts import BrokerageCredentials
from integrations.brokerage.providers.snaptrade import SnapTradeBrokerageAdapter
from integrations.exceptions import (
    IntegrationConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)


def response(body=None, status=200):
    return SimpleNamespace(body=body, status=status)


class SnapTradeAdapterTests(SimpleTestCase):
    def setUp(self):
        self.client = SimpleNamespace(
            api_status=SimpleNamespace(check=Mock(return_value=response({"version": "1"}))),
            authentication=SimpleNamespace(
                register_snap_trade_user=Mock(),
                reset_snap_trade_user_secret=Mock(),
                delete_snap_trade_user=Mock(return_value=response()),
                login_snap_trade_user=Mock(),
            ),
            connections=SimpleNamespace(
                list_brokerage_authorizations=Mock(),
                refresh_brokerage_authorization=Mock(),
                remove_brokerage_authorization=Mock(return_value=response(status=204)),
            ),
            account_information=SimpleNamespace(
                list_user_accounts=Mock(),
                get_all_account_positions=Mock(),
            ),
        )
        self.adapter = SnapTradeBrokerageAdapter(
            client_id="client", consumer_key="consumer", client=self.client
        )
        self.credentials = BrokerageCredentials("app-user-id", "user-secret")

    def test_requires_partner_credentials(self):
        with self.assertRaises(IntegrationConfigurationError):
            SnapTradeBrokerageAdapter(client_id="", consumer_key="")

    def test_pinned_sdk_exposes_every_adapter_operation(self):
        client = SnapTrade(client_id="client", consumer_key="consumer")
        operations = (
            client.api_status.check,
            client.authentication.register_snap_trade_user,
            client.authentication.reset_snap_trade_user_secret,
            client.authentication.delete_snap_trade_user,
            client.authentication.login_snap_trade_user,
            client.connections.list_brokerage_authorizations,
            client.connections.refresh_brokerage_authorization,
            client.connections.remove_brokerage_authorization,
            client.account_information.list_user_accounts,
            client.account_information.get_all_account_positions,
        )

        self.assertTrue(all(callable(operation) for operation in operations))

    def test_register_and_rotate_user_secret(self):
        self.client.authentication.register_snap_trade_user.return_value = response(
            {"userId": "app-user-id", "userSecret": "first-secret"}
        )
        self.client.authentication.reset_snap_trade_user_secret.return_value = response(
            {"userId": "app-user-id", "userSecret": "second-secret"}
        )

        registered = self.adapter.register_user("app-user-id")
        rotated = self.adapter.rotate_user_secret(registered)

        self.assertEqual(registered.user_secret, "first-secret")
        self.assertEqual(rotated.user_secret, "second-secret")
        self.assertNotIn("first-secret", repr(registered))
        self.client.authentication.register_snap_trade_user.assert_called_once_with(
            body={"userId": "app-user-id"}
        )

    def test_register_rejects_missing_secret(self):
        self.client.authentication.register_snap_trade_user.return_value = response(
            {"userId": "app-user-id"}
        )
        with self.assertRaises(ProviderResponseError):
            self.adapter.register_user("app-user-id")

    def test_connection_portal_and_connections_are_normalized(self):
        self.client.authentication.login_snap_trade_user.return_value = response(
            {"redirectURI": "https://connect.example/token"}
        )
        self.client.connections.list_brokerage_authorizations.return_value = response(
            [
                {
                    "id": "connection-1",
                    "name": "My brokerage",
                    "type": "read",
                    "disabled": False,
                    "created_date": "2025-01-01T00:00:00Z",
                    "data_freshness_mode": "realtime",
                    "brokerage": {
                        "name": "Interactive Brokers",
                        "display_name": "IBKR",
                        "slug": "INTERACTIVE_BROKERS",
                    },
                }
            ]
        )

        portal = self.adapter.create_connection_portal(
            self.credentials, broker="INTERACTIVE_BROKERS"
        )
        connections = self.adapter.list_connections(self.credentials)

        self.assertEqual(portal.redirect_url, "https://connect.example/token")
        self.assertEqual(connections[0].provider_connection_id, "connection-1")
        self.assertEqual(connections[0].brokerage_name, "IBKR")
        self.assertEqual(connections[0].created_at.tzinfo, timezone.utc)

    def test_accounts_are_normalized_without_deprecated_meta(self):
        self.client.account_information.list_user_accounts.return_value = response(
            [
                {
                    "id": "account-1",
                    "brokerage_authorization": "connection-1",
                    "name": "TFSA",
                    "number": "***1234",
                    "institution_name": "Example Broker",
                    "institution_account_id": "stable-account-id",
                    "raw_type": "TFSA",
                    "account_category": "INVESTMENT",
                    "status": "open",
                    "balance": {"total": "12500.25", "currency": "CAD"},
                    "is_paper": False,
                    "sync_status": {"holdings": {"initial_sync_completed": True}},
                    "meta": {"deprecated": "ignored"},
                }
            ]
        )

        account = self.adapter.list_accounts(self.credentials)[0]

        self.assertEqual(account.provider_account_id, "account-1")
        self.assertEqual(account.provider_value, Decimal("12500.25"))
        self.assertEqual(account.currency, "CAD")
        self.assertNotIn("meta", account.metadata)

    def test_current_position_payload_is_normalized(self):
        self.client.account_information.get_all_account_positions.return_value = response(
            {
                "results": [
                    {
                        "instrument": {
                            "kind": "stock",
                            "id": "security-1",
                            "symbol": "AAPL",
                            "raw_symbol": "AAPL",
                            "description": "Apple Inc.",
                            "currency": "USD",
                            "exchange": "NASDAQ",
                        },
                        "units": "10.5",
                        "price": "200.25",
                        "cost_basis": "150.50",
                        "currency": "USD",
                    }
                ],
                "data_freshness": {"as_of": "2025-01-01T00:00:00Z"},
            }
        )

        result = self.adapter.list_positions(self.credentials, "account-1")
        position = result.positions[0]

        self.assertEqual(position.provider_security_id, "security-1")
        self.assertIsNone(position.provider_position_id)
        self.assertEqual(position.quantity, Decimal("10.5"))
        self.assertEqual(position.average_cost, Decimal("150.50"))
        self.assertEqual(position.provider_value, Decimal("2102.625"))
        self.assertEqual(position.security_type, "stock")

    def test_legacy_position_payload_is_still_normalized(self):
        self.client.account_information.get_all_account_positions.return_value = response(
            [
                {
                    "id": "position-1",
                    "symbol": {
                        "id": "security-1",
                        "symbol": "VAB.TO",
                        "raw_symbol": "VAB",
                        "description": "Vanguard Bond ETF",
                        "currency": {"code": "CAD"},
                        "exchange": {"code": "TSX"},
                        "type": "ETF",
                    },
                    "units": "2",
                    "price": "25",
                    "average_purchase_price": "20",
                }
            ]
        )

        position = self.adapter.list_positions(
            self.credentials, "account-1"
        ).positions[0]

        self.assertEqual(position.provider_position_id, "position-1")
        self.assertEqual(position.raw_symbol, "VAB")
        self.assertEqual(position.currency, "CAD")
        self.assertEqual(position.exchange, "TSX")

    def test_disconnect_and_refresh_use_stable_connection_id(self):
        self.client.connections.refresh_brokerage_authorization.return_value = response(
            {"detail": "refresh queued"}
        )

        refreshed = self.adapter.refresh_connection(self.credentials, "connection-1")
        self.adapter.disconnect(self.credentials, "connection-1")

        self.assertEqual(refreshed, {"detail": "refresh queued"})
        self.client.connections.remove_brokerage_authorization.assert_called_once_with(
            authorization_id="connection-1",
            user_id="app-user-id",
            user_secret="user-secret",
        )

    def test_sdk_http_errors_are_normalized(self):
        cases = [
            (403, ProviderAuthenticationError),
            (404, ResourceNotFoundError),
            (429, ProviderRateLimitError),
            (503, ProviderUnavailableError),
            (422, ProviderResponseError),
        ]
        for status, expected in cases:
            self.client.api_status.check.side_effect = ApiException(
                status=status, reason="provider detail"
            )
            with self.subTest(status=status), self.assertRaises(expected):
                self.adapter.check_status()
