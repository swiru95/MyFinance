"""Timestamp helpers shared by schemas and routes."""
from datetime import datetime, timezone


def as_utc(value: datetime | None) -> datetime | None:
    """Tag a naive datetime as UTC.

    Rows written before timestamps were stored tz-aware are naive UTC; without
    this the browser reads them as local time and shows them hours off.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
