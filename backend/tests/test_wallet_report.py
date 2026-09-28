"""services.wallet_report.build_snapshot: the value-over-time chart must end
on the same live-priced total the "Total value" figure above it shows (they
used to disagree - the chart walked *stored* snapshot values while the
total was revalued live), the chart is scoped to the report's own period,
and "data as of" uses the app's configured timezone, not UTC.
"""
from datetime import datetime, timezone

import pytest

from src.services import wallet_report


def _asset(client, **overrides):
    payload = {"name": "Bitcoin", "kind": "crypto", "units": "BTC"}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_chart_last_point_matches_the_live_total_not_the_stale_snapshot(client, monkeypatch, db):
    """Mirrors test_asset_growth.py's own "value follows today's price"
    case: a BTC position bought at 65000 USD, then the price moves to
    80000 USD with no new snapshot written. The chart's stored last point
    would still be priced at 65000 - the live total is not - so this checks
    build_snapshot's chart ends on the live figure instead."""
    from src.services import price_service as ps

    asset = _asset(client)
    r = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1, "currency": "PLN"}
    )
    assert r.status_code == 201, r.text

    monkeypatch.setitem(ps._FALLBACK_CRYPTO_USD, "BTC", 80000.0)
    ps._CACHE.clear()

    snap = wallet_report.build_snapshot(db, "all")
    assert snap["value_over_time"][-1]["total"] == pytest.approx(snap["total_value"])
    # And that live figure is in fact the repriced one, not the stale 65000
    # price the snapshot was written at - otherwise this would pass
    # trivially without the fix doing anything.
    assert snap["total_value"] == pytest.approx(1 * 80000.0 * 3.95, rel=1e-4)


def test_chart_is_scoped_to_the_period_cutoff(client, db):
    """A one-month report's chart must not include days from a year ago -
    only from the period's own `since` cutoff onward."""
    asset = _asset(client, name="Cash", kind="currency", units="")
    r = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 100, "currency": "PLN"}
    )
    assert r.status_code == 201, r.text
    pos_id = r.json()["id"]
    # Backdate this one snapshot's timestamp well outside any period_start
    # cutoff shorter than "all", so the chart for period="1m" should not
    # reach back to it as a *separate* early point (it still carries
    # forward as the flat opening value, which is correct - but the point
    # count/date range must start at the cutoff, not a year ago).
    from src.models.position import Position

    row = db.query(Position).filter(Position.id == pos_id).first()
    row.timestamp = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db.commit()

    from src.services.efficiency import period_start
    from src.routes.helpers import today_in

    today = today_in(db)
    since = period_start("1m", today)

    snap = wallet_report.build_snapshot(db, "1m")
    dates = [p["date"] for p in snap["value_over_time"]]
    assert min(dates) == since.isoformat()
    assert max(dates) == today.isoformat()

    snap_all = wallet_report.build_snapshot(db, "all")
    dates_all = [p["date"] for p in snap_all["value_over_time"]]
    assert min(dates_all) == "2020-01-01"


def test_generated_at_uses_the_configured_timezone_not_utc(client, db):
    """Default timezone is Europe/Warsaw (see config.DEFAULT_TIMEZONE) -
    generated_at must carry that zone's offset, not a bare UTC "+00:00"."""
    snap = wallet_report.build_snapshot(db, "all")
    generated_at = datetime.fromisoformat(snap["generated_at"])
    assert generated_at.utcoffset() != timezone.utc.utcoffset(None)
    assert str(generated_at.tzinfo) != "UTC"
