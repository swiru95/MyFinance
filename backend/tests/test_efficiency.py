"""services.efficiency: period cutoffs and period-scoped "your money vs
growth", built directly against the `db` session (not the API) so each
snapshot's timestamp can be pinned exactly rather than left at "now" -
positions.py's own /growth endpoint has no way to backdate a snapshot.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from src.models.asset import Asset
from src.models.position import Position
from src.services import efficiency


def _asset(db, name="Brokerage", kind="currency", category="Cash"):
    a = Asset(name=name, kind=kind, category=category, profile="safe", units="")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _snapshot(db, asset, days_ago, value, flow=None, currency="PLN"):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=days_ago)
    p = Position(
        asset_id=asset.id, amount=value, currency=currency,
        value_in_base=value, price_used=1.0, base_currency=currency,
        flow_in_base=flow, timestamp=ts,
    )
    db.add(p)
    db.commit()
    return p


TODAY = date(2026, 1, 1)


# --- period_start -----------------------------------------------------

def test_period_start_all_is_none():
    assert efficiency.period_start("all", TODAY) == None  # noqa: E711


def test_period_start_last_month_is_one_month_back():
    assert efficiency.period_start("1m", TODAY) == date(2025, 12, 1)


def test_period_start_quarter_is_three_months_back():
    assert efficiency.period_start("3m", TODAY) == date(2025, 10, 1)


def test_period_start_twelve_months_is_one_year_back():
    assert efficiency.period_start("12m", TODAY) == date(2025, 1, 1)


def test_period_start_ytd_is_last_day_of_prior_year():
    assert efficiency.period_start("ytd", TODAY) == date(2025, 12, 31)


def test_period_start_clamps_short_months():
    """Aug 31 minus 6 months has no "Feb 31" - it clamps to Feb 28 (2025 is
    not a leap year)."""
    assert efficiency.period_start("3m", date(2025, 8, 31)) == date(2025, 5, 31)
    assert efficiency._subtract_months(date(2025, 8, 31), 6) == date(2025, 2, 28)


# --- period_efficiency: since cuts off correctly -----------------------

def test_period_only_counts_flows_after_the_cutoff(db):
    """A snapshot from 400 days ago (well before the 12-month cutoff)
    becomes the period's own opening value rather than a deposit; only the
    two snapshots inside the trailing 12 months count as this period's
    deposits."""
    asset = _asset(db)
    _snapshot(db, asset, days_ago=400, value=1000.0)              # opening
    _snapshot(db, asset, days_ago=200, value=1200.0, flow=100.0)  # in-period deposit
    _snapshot(db, asset, days_ago=10, value=1500.0, flow=50.0)    # in-period deposit

    result = efficiency.period_efficiency(db, "12m", TODAY)
    row = result["assets"][0]
    assert row["opening_value"] == pytest.approx(1000.0)
    assert row["contributed"] == pytest.approx(150.0)
    assert row["invested"] == pytest.approx(1150.0)
    assert row["value"] == pytest.approx(1500.0)
    assert row["growth"] == pytest.approx(350.0)
    # growth_pct is rounded to 4dp by services/growth.py before it gets here.
    assert row["growth_pct"] == pytest.approx(350.0 / 1150.0, abs=1e-4)


def test_asset_opened_during_the_period_has_no_carried_opening(db):
    """An asset whose first-ever snapshot falls inside the period behaves
    like the whole-history case: that first snapshot is the opening, not a
    deposit on top of a zero opening."""
    asset = _asset(db, name="New brokerage")
    _snapshot(db, asset, days_ago=30, value=500.0)
    _snapshot(db, asset, days_ago=5, value=600.0, flow=100.0)

    result = efficiency.period_efficiency(db, "3m", TODAY)
    row = result["assets"][0]
    assert row["opening_value"] == pytest.approx(500.0)
    assert row["contributed"] == pytest.approx(100.0)
    assert row["growth"] == pytest.approx(0.0)


def test_all_time_matches_growth_endpoint_with_no_since(db, client):
    """period="all" (since=None) must reproduce exactly what
    /api/positions/growth already reports for the same data - the PDF must
    never disagree with the Assets page."""
    a1 = client.post(
        "/api/assets", json={"name": "Brokerage", "kind": "currency", "units": ""}
    ).json()
    p1 = client.post(
        "/api/positions", json={"asset_id": a1["id"], "amount": 1000, "currency": "PLN"}
    ).json()
    client.put(
        f"/api/positions/{p1['id']}",
        json={"amount": 1120, "currency": "PLN", "flow": 100},
    )
    a2 = client.post(
        "/api/assets", json={"name": "Savings", "kind": "currency", "units": ""}
    ).json()
    client.post(
        "/api/positions", json={"asset_id": a2["id"], "amount": 500, "currency": "PLN"}
    )

    growth_endpoint = client.get("/api/positions/growth").json()
    eff = efficiency.period_efficiency(db, "all", date(2030, 1, 1))

    assert eff["total"]["invested"] == pytest.approx(growth_endpoint["total"]["invested"])
    assert eff["total"]["value"] == pytest.approx(growth_endpoint["total"]["value"])
    assert eff["total"]["growth"] == pytest.approx(growth_endpoint["total"]["growth"])
    assert eff["total"]["growth_pct"] == pytest.approx(growth_endpoint["total"]["growth_pct"])


def test_no_positions_gives_empty_assets_and_no_annualized_return(db):
    result = efficiency.period_efficiency(db, "all", TODAY)
    assert result["assets"] == []
    assert result["total"]["value"] == 0
    assert result["annualized_return"] is None


def test_result_is_json_serializable_even_with_two_or_more_snapshots(db):
    """An asset with 2+ snapshots makes services.growth.asset_growth fill in
    a "last" field carrying two raw datetime objects - harmless for
    /api/positions/growth (FastAPI serializes those), but period_efficiency's
    result is also stored straight into Insight.snapshot via plain
    json.dumps (see services/insights.py), which chokes on a bare datetime.
    Regression test for exactly that: it must be dropped, not merely
    tolerated by luck of which callers happen to touch it."""
    asset = _asset(db)
    _snapshot(db, asset, days_ago=30, value=1000.0)
    _snapshot(db, asset, days_ago=5, value=1100.0, flow=50.0)

    result = efficiency.period_efficiency(db, "all", TODAY)
    json.dumps(result)  # must not raise
    assert "last" not in result["assets"][0]


def test_annualized_return_for_a_single_clean_deposit(db):
    """One deposit exactly one year before `today`, no interim flows: the
    XIRR of that must be the plain return, same as test_xirr's own
    single-year cases - this checks period_efficiency actually builds the
    cash flows xirr() needs, not just that xirr() itself works."""
    asset = _asset(db)
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) - timedelta(days=365)
    db.add(Position(
        asset_id=asset.id, amount=1000.0, currency="PLN", value_in_base=1000.0,
        price_used=1.0, base_currency="PLN", flow_in_base=None, timestamp=ts,
    ))
    db.commit()
    # "Value now" for a currency asset is read live off `amount`, so bump it
    # to 1100 directly rather than adding another snapshot - period="all"
    # only has this one snapshot, and its own amount is what value_of_position
    # returns.
    pos = db.query(Position).filter(Position.asset_id == asset.id).first()
    pos.amount = 1100.0
    db.commit()

    result = efficiency.period_efficiency(db, "all", TODAY)
    assert result["annualized_return"] == pytest.approx(0.10, abs=1e-4)
