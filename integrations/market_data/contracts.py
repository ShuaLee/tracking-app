from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class SecuritySearchResult:
    symbol: str
    name: str
    exchange: str = ""
    currency: str = ""
    security_type: str = ""
    identity: dict[str, Any] = field(default_factory=dict)
    stale: bool = False


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    price: Decimal
    currency: str = ""
    exchange: str = ""
    as_of: datetime | None = None
    change: Decimal | None = None
    change_percent: Decimal | None = None
    volume: Decimal | None = None
    stale: bool = False


@dataclass(frozen=True, slots=True)
class SecurityProfile:
    symbol: str
    name: str
    exchange: str = ""
    currency: str = ""
    security_type: str = ""
    sector: str = ""
    industry: str = ""
    description: str = ""
    website: str = ""
    identity: dict[str, Any] = field(default_factory=dict)
    active: bool | None = None
    stale: bool = False


@dataclass(frozen=True, slots=True)
class DividendEvent:
    symbol: str
    ex_date: date
    amount: Decimal
    adjusted_amount: Decimal | None = None
    declaration_date: date | None = None
    record_date: date | None = None
    payment_date: date | None = None
    currency: str = ""
    frequency: str = ""
    stale: bool = False


@dataclass(frozen=True, slots=True)
class QuoteBatch:
    quotes: tuple[Quote, ...]
    unavailable_symbols: tuple[str, ...] = ()
    degraded: bool = False

