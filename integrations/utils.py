from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum


def as_decimal(value, *, default=None):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def as_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def as_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float, Decimal)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def plain_data(value):
    """Convert SDK models into JSON-compatible built-in containers."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return plain_data(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain_data(item) for item in value]
    if hasattr(value, "to_dict"):
        return plain_data(value.to_dict())
    try:
        return {str(key): plain_data(item) for key, item in dict(value).items()}
    except (TypeError, ValueError):
        return str(value)

