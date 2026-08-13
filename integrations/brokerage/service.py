from django.conf import settings

from integrations.brokerage.contracts import BrokerageCredentials
from integrations.brokerage.providers.snaptrade import SnapTradeBrokerageAdapter


class BrokerageService:
    def __init__(self, *, adapter=None):
        config = settings.BROKERAGE
        self.adapter = adapter or SnapTradeBrokerageAdapter(
            client_id=config.get("SNAPTRADE_CLIENT_ID", ""),
            consumer_key=config.get("SNAPTRADE_CONSUMER_KEY", ""),
        )

    def check_status(self):
        return self.adapter.check_status()

    def register_user(self, immutable_user_id):
        user_id = self._required(immutable_user_id, "immutable user ID")
        return self.adapter.register_user(user_id)

    def rotate_user_secret(self, credentials):
        return self.adapter.rotate_user_secret(self._credentials(credentials))

    def delete_user(self, credentials):
        return self.adapter.delete_user(self._credentials(credentials))

    def create_connection_portal(self, credentials, **options):
        return self.adapter.create_connection_portal(
            self._credentials(credentials), **options
        )

    def list_connections(self, credentials):
        return self.adapter.list_connections(self._credentials(credentials))

    def refresh_connection(self, credentials, connection_id):
        return self.adapter.refresh_connection(
            self._credentials(credentials), self._required(connection_id, "connection ID")
        )

    def disconnect(self, credentials, connection_id):
        return self.adapter.disconnect(
            self._credentials(credentials), self._required(connection_id, "connection ID")
        )

    def list_accounts(self, credentials):
        return self.adapter.list_accounts(self._credentials(credentials))

    def list_positions(self, credentials, account_id):
        return self.adapter.list_positions(
            self._credentials(credentials), self._required(account_id, "account ID")
        )

    @staticmethod
    def _credentials(credentials):
        if not isinstance(credentials, BrokerageCredentials):
            raise TypeError("BrokerageCredentials are required.")
        if not credentials.user_id or not credentials.user_secret:
            raise ValueError("Brokerage user ID and secret are required.")
        return credentials

    @staticmethod
    def _required(value, label):
        normalized = str(value).strip()
        if not normalized:
            raise ValueError(f"A valid {label} is required.")
        return normalized

