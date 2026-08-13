from unittest.mock import Mock

from django.test import SimpleTestCase

from integrations.brokerage.contracts import BrokerageCredentials
from integrations.brokerage.service import BrokerageService


class BrokerageServiceTests(SimpleTestCase):
    def setUp(self):
        self.adapter = Mock()
        self.service = BrokerageService(adapter=self.adapter)
        self.credentials = BrokerageCredentials("user-id", "secret")

    def test_delegates_provider_lifecycle_and_read_operations(self):
        self.service.register_user(" immutable-id ")
        self.service.create_connection_portal(self.credentials, broker="IBKR")
        self.service.list_connections(self.credentials)
        self.service.refresh_connection(self.credentials, "connection-id")
        self.service.list_accounts(self.credentials)
        self.service.list_positions(self.credentials, "account-id")
        self.service.disconnect(self.credentials, "connection-id")
        self.service.rotate_user_secret(self.credentials)

        self.adapter.register_user.assert_called_once_with("immutable-id")
        self.adapter.create_connection_portal.assert_called_once_with(
            self.credentials, broker="IBKR"
        )
        self.adapter.list_positions.assert_called_once_with(
            self.credentials, "account-id"
        )

    def test_rejects_untyped_or_incomplete_credentials(self):
        with self.assertRaises(TypeError):
            self.service.list_accounts({"user_id": "x", "user_secret": "y"})
        with self.assertRaises(ValueError):
            self.service.list_accounts(BrokerageCredentials("x", ""))

    def test_rejects_empty_identifiers(self):
        with self.assertRaises(ValueError):
            self.service.register_user(" ")
        with self.assertRaises(ValueError):
            self.service.list_positions(self.credentials, " ")

