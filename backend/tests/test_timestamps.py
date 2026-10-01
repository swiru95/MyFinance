"""Timestamp columns hold naive UTC, whatever the caller (or the database
server's time zone) is.

The columns are `TIMESTAMP WITHOUT TIME ZONE` and the application's own defaults
are tz-aware (`datetime.now(timezone.utc)`). PostgreSQL turns an aware value
into the column's zone-less form using the *session's* TimeZone, so before
models/types.UtcDateTime a snapshot written as 2020-01-01T00:00Z came back as
2019-12-31 on a server set to New York. See also
test_efficiency::test_annualized_return_for_a_single_clean_deposit and
test_wallet_report::test_chart_is_scoped_to_the_period_cutoff, which tripped
over exactly that.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, text

from src.models import Asset, Position


def _position(asset_id, ts):
    return Position(
        asset_id=asset_id, amount=1, currency="PLN", value_in_base=1, price_used=1,
        base_currency="PLN", timestamp=ts,
    )


@pytest.mark.parametrize("zone", ["UTC", "America/New_York", "Pacific/Auckland", "Asia/Kolkata"])
def test_an_aware_datetime_is_stored_as_naive_utc_whatever_the_session_time_zone(db, zone):
    if db.get_bind().dialect.name == "postgresql":
        # The session setting that used to leak into the stored value.
        db.execute(text(f"SET LOCAL TIME ZONE '{zone}'"))
    asset = Asset(name="Cash", kind="currency")
    db.add(asset)
    db.flush()
    plus_two = timezone(timedelta(hours=2))
    db.add_all([
        _position(asset.id, datetime(2020, 1, 1, tzinfo=timezone.utc)),
        _position(asset.id, datetime(2020, 6, 1, 12, 0, tzinfo=plus_two)),
        _position(asset.id, datetime(2021, 3, 4, 5, 6, 7)),  # already naive: untouched
    ])
    db.commit()

    stored = [r[0] for r in db.query(Position.timestamp).order_by(Position.id)]
    assert stored == [
        datetime(2020, 1, 1, 0, 0),
        datetime(2020, 6, 1, 10, 0),
        datetime(2021, 3, 4, 5, 6, 7),
    ]
    assert all(ts.tzinfo is None for ts in stored)


def test_comparing_a_column_with_an_aware_datetime_uses_utc_too(db):
    asset = Asset(name="Cash", kind="currency")
    db.add(asset)
    db.flush()
    db.add(_position(asset.id, datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)))
    db.commit()
    plus_two = timezone(timedelta(hours=2))
    # 13:00+02:00 is 11:00 UTC: before the row; 15:00+02:00 is 13:00 UTC: after it.
    assert db.query(func.count(Position.id)).filter(Position.timestamp > datetime(2020, 1, 1, 13, tzinfo=plus_two)).scalar() == 1
    assert db.query(func.count(Position.id)).filter(Position.timestamp > datetime(2020, 1, 1, 15, tzinfo=plus_two)).scalar() == 0
