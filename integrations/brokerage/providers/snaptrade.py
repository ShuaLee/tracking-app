from snaptrade_client import SnapTrade
from snaptrade_client.exceptions import ApiException, OpenApiException
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from integrations.brokerage.contracts import (
    AccountPositions,
    BrokerageCredentials,
    ConnectionPortal,
    NormalizedBrokerageAccount,
    NormalizedBrokerageConnection,
    NormalizedPosition,
)
from integrations.exceptions import (
    IntegrationConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
    ResourceNotFoundError,
)
from integrations.utils import as_datetime, as_decimal, plain_data


class SnapTradeBrokerageAdapter:
    provider_name = "snaptrade"

    def __init__(self, *, client_id, consumer_key, client=None):
        if not client_id or not consumer_key:
            raise IntegrationConfigurationError(
                "SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY must be configured."
            )
        self.client = client or SnapTrade(client_id=client_id, consumer_key=consumer_key)

    def check_status(self):
        return self._body(self._call(self.client.api_status.check))

    def register_user(self, user_id):
        body = self._body(
            self._call(
                self.client.authentication.register_snap_trade_user,
                body={"userId": user_id},
            )
        )
        if not isinstance(body, dict) or not body.get("userSecret"):
            raise ProviderResponseError("SnapTrade did not return a user secret.")
        return BrokerageCredentials(
            user_id=str(body.get("userId") or user_id),
            user_secret=str(body["userSecret"]),
        )

    def rotate_user_secret(self, credentials):
        body = self._body(
            self._call(
                self.client.authentication.reset_snap_trade_user_secret,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
            )
        )
        if not isinstance(body, dict) or not body.get("userSecret"):
            raise ProviderResponseError("SnapTrade did not return a replacement user secret.")
        return BrokerageCredentials(
            user_id=str(body.get("userId") or credentials.user_id),
            user_secret=str(body["userSecret"]),
        )

    def delete_user(self, credentials):
        self._call(
            self.client.authentication.delete_snap_trade_user,
            user_id=credentials.user_id,
        )

    def create_connection_portal(
        self,
        credentials,
        *,
        broker=None,
        custom_redirect=None,
        reconnect=None,
        connection_type="read",
    ):
        body = self._body(
            self._call(
                self.client.authentication.login_snap_trade_user,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
                broker=broker,
                custom_redirect=custom_redirect,
                reconnect=reconnect,
                connection_type=connection_type,
            )
        )
        if not isinstance(body, dict) or not body.get("redirectURI"):
            raise ProviderResponseError("SnapTrade did not return a connection portal URL.")
        return ConnectionPortal(redirect_url=str(body["redirectURI"]))

    def list_connections(self, credentials):
        body = self._body(
            self._call(
                self.client.connections.list_brokerage_authorizations,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
            )
        )
        if not isinstance(body, list):
            raise ProviderResponseError("SnapTrade returned an invalid connections payload.")
        return [self._connection(item) for item in body if isinstance(item, dict)]

    def refresh_connection(self, credentials, connection_id):
        return self._body(
            self._call(
                self.client.connections.refresh_brokerage_authorization,
                authorization_id=connection_id,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
            )
        )

    def disconnect(self, credentials, connection_id):
        self._call(
            self.client.connections.remove_brokerage_authorization,
            authorization_id=connection_id,
            user_id=credentials.user_id,
            user_secret=credentials.user_secret,
        )

    def list_accounts(self, credentials):
        body = self._body(
            self._call(
                self.client.account_information.list_user_accounts,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
            )
        )
        if not isinstance(body, list):
            raise ProviderResponseError("SnapTrade returned an invalid accounts payload.")
        return [self._account(item) for item in body if isinstance(item, dict)]

    def list_positions(self, credentials, account_id):
        body = self._body(
            self._call(
                self.client.account_information.get_all_account_positions,
                user_id=credentials.user_id,
                user_secret=credentials.user_secret,
                account_id=account_id,
            )
        )
        data_freshness = {}
        if isinstance(body, dict):
            results = body.get("results", [])
            data_freshness = body.get("data_freshness") or {}
        elif isinstance(body, list):
            results = body
        else:
            raise ProviderResponseError("SnapTrade returned an invalid positions payload.")
        positions = tuple(
            self._position(item) for item in results if isinstance(item, dict)
        )
        return AccountPositions(
            account_id=account_id,
            positions=positions,
            data_freshness=plain_data(data_freshness),
        )

    def _call(self, method, **kwargs):
        try:
            response = method(**{key: value for key, value in kwargs.items() if value is not None})
        except ApiException as exc:
            status = exc.status or 0
            if status in {401, 403}:
                raise ProviderAuthenticationError("SnapTrade credentials were rejected.") from exc
            if status == 404:
                raise ResourceNotFoundError("SnapTrade resource was not found.") from exc
            if status == 429:
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                raise ProviderRateLimitError(
                    "SnapTrade rate limit was reached.", retry_after=retry_after
                ) from exc
            if status >= 500:
                raise ProviderUnavailableError("SnapTrade is temporarily unavailable.") from exc
            raise ProviderResponseError(f"SnapTrade returned HTTP {status}.") from exc
        except (Urllib3HTTPError, TimeoutError, ConnectionError) as exc:
            raise ProviderUnavailableError("SnapTrade could not be reached.") from exc
        except OpenApiException as exc:
            raise ProviderResponseError("SnapTrade SDK rejected the response or request.") from exc
        status = getattr(response, "status", 200)
        if status and status >= 400:
            raise ProviderResponseError(f"SnapTrade returned HTTP {status}.")
        return response

    @staticmethod
    def _body(response):
        return plain_data(getattr(response, "body", response))

    @staticmethod
    def _connection(item):
        brokerage = item.get("brokerage") if isinstance(item.get("brokerage"), dict) else {}
        return NormalizedBrokerageConnection(
            provider_connection_id=str(item.get("id") or ""),
            name=str(item.get("name") or brokerage.get("display_name") or brokerage.get("name") or "Brokerage"),
            brokerage_name=str(brokerage.get("display_name") or brokerage.get("name") or ""),
            brokerage_slug=str(brokerage.get("slug") or ""),
            connection_type=str(item.get("type") or ""),
            disabled=bool(item.get("disabled", False)),
            created_at=as_datetime(item.get("created_date")),
            metadata={
                "data_freshness_mode": item.get("data_freshness_mode"),
                "disabled_date": plain_data(item.get("disabled_date")),
            },
        )

    @staticmethod
    def _account(item):
        balance = item.get("balance")
        if isinstance(balance, dict):
            total = balance.get("total")
            if isinstance(total, dict):
                provider_value = as_decimal(total.get("amount"))
                currency = str(total.get("currency") or "").upper()
            else:
                provider_value = as_decimal(total)
                currency = str(balance.get("currency") or "").upper()
        else:
            provider_value = as_decimal(balance)
            currency = ""
        return NormalizedBrokerageAccount(
            provider_account_id=str(item.get("id") or ""),
            provider_connection_id=str(item.get("brokerage_authorization") or ""),
            name=str(item.get("name") or "Brokerage Account"),
            institution=str(item.get("institution_name") or ""),
            currency=currency,
            masked_number=str(item.get("number") or ""),
            institution_account_id=(
                str(item["institution_account_id"])
                if item.get("institution_account_id") is not None
                else None
            ),
            account_type=str(item.get("raw_type") or ""),
            account_category=str(item.get("account_category") or ""),
            status=str(item.get("status") or ""),
            provider_value=provider_value,
            is_paper=bool(item.get("is_paper", False)),
            metadata={"sync_status": plain_data(item.get("sync_status") or {})},
        )

    @staticmethod
    def _position(item):
        instrument = item.get("instrument")
        if not isinstance(instrument, dict):
            instrument = item.get("symbol") if isinstance(item.get("symbol"), dict) else {}
        universal = instrument.get("symbol") if isinstance(instrument.get("symbol"), dict) else instrument
        quantity = as_decimal(item.get("units"), default=as_decimal(item.get("quantity"), default=0))
        price = as_decimal(item.get("price"))
        average_cost = as_decimal(item.get("cost_basis"), default=as_decimal(item.get("average_purchase_price")))
        provider_value = price * quantity if price is not None and quantity is not None else None
        currency_value = universal.get("currency")
        if isinstance(currency_value, dict):
            currency_value = currency_value.get("code")
        exchange_value = universal.get("exchange")
        if isinstance(exchange_value, dict):
            exchange_value = exchange_value.get("code") or exchange_value.get("mic_code")
        symbol = str(universal.get("symbol") or universal.get("raw_symbol") or "")
        raw_symbol = str(universal.get("raw_symbol") or symbol)
        return NormalizedPosition(
            provider_position_id=(str(item["id"]) if item.get("id") is not None else None),
            provider_security_id=(
                str(universal["id"]) if universal.get("id") is not None else None
            ),
            symbol=symbol,
            raw_symbol=raw_symbol,
            name=str(universal.get("description") or symbol),
            quantity=quantity,
            average_cost=average_cost,
            currency=str(item.get("currency") or currency_value or "").upper(),
            exchange=str(exchange_value or ""),
            security_type=str(universal.get("kind") or universal.get("type") or ""),
            provider_price=price,
            provider_value=provider_value,
            metadata={
                "cash_equivalent": bool(item.get("cash_equivalent", False)),
                "figi": plain_data(universal.get("figi_instrument")),
            },
        )
