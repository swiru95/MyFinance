"""Day/hour-billed B2B sources: the working-time calendar drives the default
revenue, a fixed units_per_month or an entry's units can override it, and the
comparator's working_days falls back to the calendar total."""
from src.tax.pl.calendar import working_days as calendar_working_days
from src.tax.pl.calendar import working_hours as calendar_working_hours


def _create_daily_source(client, **param_overrides):
    params = {
        "billing": "daily",
        "rate": 100.0,
        "costs_monthly": 0,
        "tax_form": "liniowy",
        "zus_stage": "full",
    }
    params.update(param_overrides)
    payload = {
        "name": "Contract",
        "kind": "b2b",
        "currency": "PLN",
        "params": params,
        "starts_on": "2026-01-01",
    }
    r = client.post("/api/income/sources", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _month_row(client, source_id, year, month):
    body = client.get(f"/api/income/sources/{source_id}/year/{year}").json()
    return next(m for m in body["months"] if m["month"] == f"{year:04d}-{month:02d}")


def test_daily_source_with_no_units_per_month_bills_calendar_working_days(client):
    src = _create_daily_source(client)
    jan = _month_row(client, src["id"], 2026, 1)
    expected_days = calendar_working_days(2026, 1)
    assert jan["amount"] == 100.0 * expected_days
    assert jan["units"] == expected_days
    assert jan["units_source"] == "calendar"
    assert jan["working_days"] == expected_days
    assert jan["working_hours"] == calendar_working_hours(2026, 1)


def test_entry_with_units_bills_rate_times_units_and_marks_entry_source(client):
    src = _create_daily_source(client)
    r = client.put(f"/api/income/sources/{src['id']}/entries/2026-03", json={"units": 10})
    assert r.status_code == 200
    assert r.json()["amount"] == 1_000.0
    assert r.json()["units"] == 10.0

    march = _month_row(client, src["id"], 2026, 3)
    assert march["amount"] == 1_000.0
    assert march["units"] == 10.0
    assert march["units_source"] == "entry"


def test_explicit_entry_amount_wins_over_units(client):
    src = _create_daily_source(client)
    r = client.put(
        f"/api/income/sources/{src['id']}/entries/2026-04",
        json={"amount": 5_000, "units": 10},
    )
    assert r.status_code == 200
    # amount (5 000) wins over rate x units (100 x 10 = 1 000).
    assert r.json()["amount"] == 5_000.0


def test_fixed_units_per_month_wins_over_calendar(client):
    src = _create_daily_source(client, units_per_month=15)
    jan = _month_row(client, src["id"], 2026, 1)
    assert jan["amount"] == 100.0 * 15
    assert jan["units"] == 15.0
    assert jan["units_source"] == "fixed"


def test_uop_entry_without_amount_is_422(client):
    payload = {
        "name": "Job",
        "kind": "uop",
        "currency": "PLN",
        "params": {"gross_monthly": 10_000},
        "starts_on": "2026-01-01",
    }
    r = client.post("/api/income/sources", json=payload)
    assert r.status_code == 201
    src = r.json()

    r = client.put(f"/api/income/sources/{src['id']}/entries/2026-02", json={})
    assert r.status_code == 422


def test_daily_entry_without_amount_or_units_is_422(client):
    src = _create_daily_source(client)
    r = client.put(f"/api/income/sources/{src['id']}/entries/2026-05", json={})
    assert r.status_code == 422


def test_compare_without_working_days_uses_calendar_total_for_2026(client):
    r = client.post(
        "/api/tax/compare",
        json={
            "year": 2026,
            "uop_gross_monthly": 10_000,
            "b2b_revenue_monthly": 13_000,
            "b2b_costs_monthly": 500,
        },
    )
    assert r.status_code == 200
    assert r.json()["working_days"] == 251


def test_get_calendar_endpoint_2026(client):
    r = client.get("/api/tax/calendar/2026")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 12
    assert sum(m["working_days"] for m in body) == 251
    assert sum(m["working_hours"] for m in body) == 2008
