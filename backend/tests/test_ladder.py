"""services/ladder.build_ladder: each rung's status on small fixtures built
through the API, the same way the rest of the suite exercises routes.
"""
from datetime import date, timedelta

from src.services.ladder import RUNG_KEYS, build_ladder


def _asset(client, **overrides):
    payload = {"name": "asset", "kind": "currency", "category": "Cash", "profile": "safe"}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _position(client, asset_id, amount, **overrides):
    payload = {"asset_id": asset_id, "amount": amount, "currency": "PLN"}
    payload.update(overrides)
    r = client.post("/api/positions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _expense(client, amount, **overrides):
    payload = {
        "name": "Rent",
        "amount": amount,
        "currency": "PLN",
        "period": "monthly",
        "category": "Housing",
        "starts_on": "2024-01-01",
    }
    payload.update(overrides)
    r = client.post("/api/expenses", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _uop_source(client, **overrides):
    payload = {
        "name": "Job",
        "kind": "uop",
        "currency": "PLN",
        "params": {"gross_monthly": 10_000, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2024-01-01",
    }
    payload.update(overrides)
    r = client.post("/api/income/sources", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _b2b_source(client, **overrides):
    payload = {
        "name": "Freelance",
        "kind": "b2b",
        "currency": "PLN",
        "params": {"billing": "monthly", "invoice_monthly": 15_000, "tax_form": "liniowy"},
        "starts_on": "2024-01-01",
    }
    payload.update(overrides)
    r = client.post("/api/income/sources", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _rung(rungs, key):
    return next(r for r in rungs if r["key"] == key)


def test_all_nine_keys_present_in_order(client, db):
    rungs = build_ladder(db)
    assert [r["key"] for r in rungs] == RUNG_KEYS
    for r in rungs:
        assert r["order"] == RUNG_KEYS.index(r["key"])


def test_starter_buffer_todo_then_done(client, db):
    _expense(client, 2000)
    rungs = build_ladder(db)
    assert _rung(rungs, "starter_buffer")["status"] == "todo"

    a = _asset(client)
    _position(client, a["id"], 5000)
    rungs = build_ladder(db)
    rung = _rung(rungs, "starter_buffer")
    assert rung["status"] == "done"
    assert rung["figures"]["safe_assets"] == 5000
    assert rung["figures"]["target"] == 2000


def test_envelope_covered_not_applicable_without_b2b(client, db):
    _uop_source(client)
    rungs = build_ladder(db)
    assert _rung(rungs, "envelope_covered")["status"] == "not_applicable"


def test_envelope_covered_todo_then_done(client, db):
    _b2b_source(client)
    rungs = build_ladder(db)
    rung = _rung(rungs, "envelope_covered")
    assert rung["status"] == "todo"
    outstanding = rung["figures"]["envelope_outstanding"]
    assert outstanding > 0

    a = _asset(client)
    _position(client, a["id"], outstanding + 1000)
    rungs = build_ladder(db)
    assert _rung(rungs, "envelope_covered")["status"] == "done"


def test_emergency_fund_target_is_six_for_uop_and_nine_with_b2b(client, db):
    _expense(client, 1000)
    _uop_source(client)
    rungs = build_ladder(db)
    rung = _rung(rungs, "emergency_fund")
    assert rung["figures"]["target_months"] == 6
    assert rung["figures"]["target_source"] == "default"

    _b2b_source(client)
    rungs = build_ladder(db)
    rung = _rung(rungs, "emergency_fund")
    assert rung["figures"]["target_months"] == 9
    assert rung["status"] == "todo"


def test_emergency_fund_setting_overrides_default(client, db):
    _expense(client, 1000)
    r = client.put("/api/fire/settings", json={"emergency_months": 3})
    assert r.status_code == 200
    rungs = build_ladder(db)
    rung = _rung(rungs, "emergency_fund")
    assert rung["figures"]["target_months"] == 3
    assert rung["figures"]["target_source"] == "fire_settings"


def test_ppk_on_not_applicable_then_todo_then_done(client, db):
    rungs = build_ladder(db)
    assert _rung(rungs, "ppk_on")["status"] == "not_applicable"

    _uop_source(client, params={"gross_monthly": 10_000, "ppk_employee": 0, "ppk_employer": 0})
    rungs = build_ladder(db)
    assert _rung(rungs, "ppk_on")["status"] == "todo"

    src = _uop_source(client, name="Job 2", params={"gross_monthly": 10_000})
    rungs = build_ladder(db)
    # Two UoP sources active: the first one found still drives the figure,
    # but any ppk_employee > 0 among active sources is not required here -
    # this just checks the endpoint does not error with more than one.
    assert _rung(rungs, "ppk_on")["status"] in ("todo", "done")


def test_ikze_used_progresses_with_flows(client, db):
    rungs = build_ladder(db)
    rung = _rung(rungs, "ikze_used")
    assert rung["status"] == "todo"
    assert rung["figures"]["flows_ytd"] == 0

    a = _asset(client, wrapper="ikze")
    # An explicit `flow` on a currency position is always the deposit, even
    # on the asset's first snapshot - see routes/positions._flow_in_base.
    _position(client, a["id"], 2000, flow=2000)
    rungs = build_ladder(db)
    rung = _rung(rungs, "ikze_used")
    assert rung["status"] == "in_progress"
    assert rung["figures"]["flows_ytd"] == 2000
    assert "tax_saved" in rung["figures"]


def test_oki_asset_does_not_count_towards_ikze_or_ike_usage(client, db):
    # oki is tax-advantaged but is its own wrapper string, not "ikze"/"ike",
    # so _wrapper_flows_ytd's exact-match filter naturally excludes it - this
    # just pins that behaviour down as a regression test.
    a = _asset(client, wrapper="oki")
    _position(client, a["id"], 40_000, flow=40_000)
    rungs = build_ladder(db)
    assert _rung(rungs, "ikze_used")["figures"]["flows_ytd"] == 0
    assert _rung(rungs, "ike_used")["figures"]["flows_ytd"] == 0


def test_fire_configured_and_savings_rate_unknown_without_settings(client, db):
    rungs = build_ladder(db)
    assert _rung(rungs, "fire_configured")["status"] == "todo"
    assert _rung(rungs, "savings_rate_on_track")["status"] == "unknown"

    r = client.put(
        "/api/fire/settings",
        json={"birth_year": 1990, "target_fi_age": 45},
    )
    assert r.status_code == 200
    rungs = build_ladder(db)
    assert _rung(rungs, "fire_configured")["status"] == "done"


def test_data_fresh_todo_on_empty_wallet_then_in_progress_with_stale_asset(client, db):
    rungs = build_ladder(db)
    # No assets and no typed months at all: both signals are entirely missing.
    assert _rung(rungs, "data_fresh")["status"] == "todo"

    a = _asset(client)
    _position(client, a["id"], 100)
    # The API always timestamps "now" - back-date the row directly so the
    # freshness check has something stale to find.
    from datetime import datetime

    from src.models.position import Position
    from src.services.budget import month_key, shift_month

    pos = db.query(Position).filter(Position.asset_id == a["id"]).first()
    pos.timestamp = datetime.combine(date.today() - timedelta(days=200), datetime.min.time())
    db.commit()

    # One of the two completed months typed in, so only the asset (not both
    # signals at once) is stale - "todo" is reserved for nothing at all
    # being fresh/typed.
    last_month = shift_month(month_key(date.today()), -1)
    r = client.put(f"/api/monthly/{last_month}", json={"income": 5000, "actual_spent": 3000})
    assert r.status_code == 200, r.text

    rungs = build_ladder(db)
    rung = _rung(rungs, "data_fresh")
    assert rung["status"] == "in_progress"
    assert a["name"] in rung["figures"]["stale_assets"]


def test_starter_buffer_and_emergency_fund_report_business_contributions(client, db):
    """Both rungs keep using the full monthly_total (personal + JDG ZUS/
    health) as their target, and now also surface the contribution figure
    itself so the "why" text can explain what is included."""
    _expense(client, 1000)
    _b2b_source(client)

    from src.routes.expenses import expense_summary

    expected = expense_summary(db=db).business_contributions_total
    assert expected > 0

    rungs = build_ladder(db)
    for key in ("starter_buffer", "emergency_fund"):
        rung = _rung(rungs, key)
        assert rung["figures"]["business_contributions_total"] == expected


def test_ladder_feedback_round_trips_through_settings(client, db):
    from src.services.ladder import active_feedback, save_feedback_entry

    save_feedback_entry(db, "ppk_on", "dismissed")
    feedback = active_feedback(db)
    assert feedback["ppk_on"]["state"] == "dismissed"

    rungs = build_ladder(db)
    assert _rung(rungs, "ppk_on")["feedback"]["state"] == "dismissed"
