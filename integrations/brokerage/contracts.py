from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class BrokerageCredentials:
    user_id: str
    user_secret: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class ConnectionPortal:
    redirect_url: str


@dataclass(frozen=True, slots=True)
class NormalizedBrokerageConnection:
    provider_connection_id: str
    name: str
    brokerage_name: str
    brokerage_slug: str = ""
    connection_type: str = ""
    disabled: bool = False
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedBrokerageAccount:
    provider_account_id: str
    provider_connection_id: str
    name: str
    institution: str
    currency: str = ""
    masked_number: str = ""
    institution_account_id: str | None = None
    account_type: str = ""
    account_category: str = ""
    status: str = ""
    provider_value: Decimal | None = None
    is_paper: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class NormalizedPosition:
    provider_position_id: str | None
    provider_security_id: str | None
    symbol: str
    raw_symbol: str
    name: str
    quantity: Decimal
    average_cost: Decimal | None = None
    currency: str = ""
    exchange: str = ""
    security_type: str = ""
    provider_price: Decimal | None = None
    provider_value: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccountPositions:
    account_id: str
    positions: tuple[NormalizedPosition, ...]
    data_freshness: dict[str, Any] = field(default_factory=dict)

