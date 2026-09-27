"""Monthly budget integration: an income source's net folds into
income_in_base alongside the typed "other income" field, months a source is
active in show up even with no saved MonthlyRecord, behaviour with no
sources at all is unchanged, and /api/income/summary's b2b envelope reports
the right due dates and outstanding status.

"Today" is frozen by monkeypatching the `today_in` name inside each route
module rather than `src.routes.helpers.today_in` itself: both
src/routes/monthly.py and src/routes/income.py did `from .helpers import
today_in`, which copies the function reference into their own namespace at
import time, so patching the shared helpers module afterwards would not
reach either of them.
"""
from datetime import date


def _freeze_today(monkeypatch, frozen: date):
    monkeypatch.setattr("src.routes.monthly.today_in", lambda db: frozen)
    monkeypatch.setattr("src.routes.income.today_in", lambda db: frozen)


def _uop_source(client, **overrides):
    payload = {
        "name": "Job",
        "kind": "uop",
        "currency": "PLN",
        "params": {"gross_monthly": 10_000, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2026-01-01",
    }
    payload.update(overrides)
    return client.post("/api/income/sources", json=payload).json()


def test_source_income_adds_to_typed_income(client, monkeypatch):
    _freeze_today(monkeypatch, date(2026, 6, 15))
    src = _uop_source(client)

    # Read the source's own figure for June as the ground truth, rather than
    # re-deriving the tax maths in the test.
    year = client.get(f"/api/income/sources/{src['id']}/year/2026").json()
    june = next(m for m in year["months"] if m["month"] == "2026-06")
    source_net = june["net_in_base"]
    assert source_net > 0

    r = client.put("/api/monthly/2026-06", json={"income": 500, "actual_spent": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["income"] == 500.0
    assert body["income_from_sources_in_base"] == source_net
    assert body["income_in_base"] == round(500.0 + source_net, 2)
    assert body["income_sources"] == [
        {
            "source_id": src["id"],
            "name": "Job",
            "kind": "uop",
            "net_in_base": source_net,
            "overridden": False,
        }
    ]
    assert body["surplus"] == round(body["income_in_base"] - body["actual_in_base"], 2)


def test_list_months_includes_source_active_months_with_no_record(client, monkeypatch):
    _freeze_today(monkeypatch, date(2026, 6, 15))
    _uop_source(client)

    r = client.get("/api/monthly")
    assert r.status_code == 200
    months = {m["month"] for m in r.json()}
    # Every month the source has been active, back to Jan 2026, gets a row
    # even though no MonthlyRecord was ever saved for it.
    assert {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"} <= months


def test_no_sources_behaviour_is_unchanged(client, monkeypatch):
    _freeze_today(monkeypatch, date(2026, 6, 15))
    r = client.put("/api/monthly/2026-06", json={"income": 8_000, "actual_spent": 5_000})
    assert r.status_code == 200
    body = r.json()
    assert body["income_from_sources_in_base"] == 0.0
    assert body["income_sources"] == []
    assert body["income_in_base"] == 8_000.0
    assert body["surplus"] == 3_000.0
    assert body["savings_rate"] == 37.5


def test_envelope_outstanding_amounts_and_due_dates(client, monkeypatch):
    # 22 June: May's ZUS/PIT (due the 20th) have passed, May's VAT (due the
    # 25th) has not, and none of June's (due in July) are due yet.
    _freeze_today(monkeypatch, date(2026, 6, 22))

    src = client.post(
        "/api/income/sources",
        json={
            "name": "Freelance",
            "kind": "b2b",
            "currency": "PLN",
            "params": {
                "billing": "monthly",
                "invoice_monthly": 10_000,
                "costs_monthly": 0,
                "tax_form": "liniowy",
                "zus_stage": "full",
            },
            "starts_on": "2026-01-01",
        },
    ).json()

    r = client.get("/api/income/summary?year=2026")
    assert r.status_code == 200
    body = r.json()

    envelope = {item["month"]: item for item in body["envelope"] if item["source_id"] == src["id"]}
    assert set(envelope) == {"2026-05", "2026-06"}

    may_item = envelope["2026-05"]
    assert may_item["zus"]["due_date"] == "2026-06-20"
    assert may_item["zus"]["status"] == "paid_window_passed"
    assert may_item["pit"]["due_date"] == "2026-06-20"
    assert may_item["pit"]["status"] == "paid_window_passed"
    assert may_item["vat"]["due_date"] == "2026-06-25"
    assert may_item["vat"]["status"] == "outstanding"

    june_item = envelope["2026-06"]
    assert june_item["zus"]["due_date"] == "2026-07-20"
    assert june_item["zus"]["status"] == "outstanding"
    assert june_item["pit"]["due_date"] == "2026-07-20"
    assert june_item["vat"]["due_date"] == "2026-07-25"

    # Outstanding total sums June's three components plus May's VAT only.
    expected = (
        june_item["zus"]["amount_in_base"]
        + june_item["pit"]["amount_in_base"]
        + june_item["vat"]["amount_in_base"]
        + may_item["vat"]["amount_in_base"]
    )
    assert body["envelope_outstanding_in_base"] == round(expected, 2)
    assert body["envelope_outstanding_in_base"] > 0


def test_months_without_typed_spend_do_not_count_as_zero_spend(client, monkeypatch):
    """Regression: source income in a month nobody typed spending into must
    not drag avg_actual or the savings rate towards 0."""
    from datetime import date

    monkeypatch.setattr("src.routes.monthly.today_in", lambda db: date(2026, 6, 15))
    client.post("/api/income/sources", json={
        "name": "Job", "kind": "other", "starts_on": "2026-01-01",
        "params": {"net_monthly": 10000},
    })
    client.put("/api/monthly/2026-06", json={"income": 0, "actual_spent": 6000, "currency": "PLN"})
    body = client.get("/api/monthly/analytics?months_back=5&months_ahead=0").json()
    assert body["months_recorded"] == 6
    assert body["months_with_spend"] == 1
    assert body["avg_actual"] == 6000
    assert body["avg_savings_rate"] == 40.0


def test_source_older_than_loaded_tax_rules_does_not_break_monthly(client, monkeypatch):
    """Regression: a source running since 2024 made /api/monthly 500, because
    the list reached back into a year with no tax rules loaded."""
    from datetime import date

    monkeypatch.setattr("src.routes.monthly.today_in", lambda db: date(2026, 9, 27))
    client.post("/api/income/sources", json={
        "name": "Job", "kind": "uop", "starts_on": "2024-01-01",
        "params": {"gross_monthly": 10000, "ppk_employee": 0, "ppk_employer": 0},
    })
    res = client.get("/api/monthly")
    assert res.status_code == 200
    months = [m["month"] for m in res.json()]
    assert min(months) == "2025-01"
    assert client.get("/api/income/sources/1/year/2024").status_code == 422
