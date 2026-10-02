"""Column types shared by the models."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator):
    """A timestamp column that holds naive UTC, whatever it is handed.

    Every timestamp column here is `TIMESTAMP WITHOUT TIME ZONE` and every
    reader treats it as UTC (timeutils.as_utc tags it on the way out). The
    application's own defaults, though, are `datetime.now(timezone.utc)` - tz
    *aware*. SQLite stores the wall-clock digits and drops the offset, which
    happens to be right. PostgreSQL does not: psycopg sends an aware value as
    `timestamptz`, and the server converts that to a column without a zone using
    *its session TimeZone*. On a server not set to UTC every stored timestamp
    came out shifted by the server's offset (a snapshot dated 2020-01-01 UTC
    read back as 2019-12-31 on a New York server); on a server that is set to
    UTC the bug was merely invisible.

    Normalising at the one place a value enters the database - here, for every
    column of this type - makes the stored value independent of the server's
    setting and of whether a caller passed an aware or a naive datetime.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
