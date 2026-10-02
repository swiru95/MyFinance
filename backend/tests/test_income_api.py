"""Income source API: source CRUD, the per-source year breakdown, entry
overrides (both the amount and the override_net path), and currency
conversion for a non-PLN source.
"""
from src.tax.pl.uop import UopOptions, uop_schedule


def _create_uop_source(client, **overrides):
    payload = {
        "name": "Job",
        "kind": "uop",
        "currency": "PLN",
        "params": {"gross_monthly": 10_000, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2026-01-01",
    }
    payload.update(overrides)
    r = client.post("/api/income/sources", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_uop_source_active_from_starts_on(client):
    src = _create_uop_source(client, starts_on="2026-04-01")
    r = client.get(f"/api/income/sources/{src['id']}/year/2026")
    assert r.status_code == 200
    body = r.json()
    assert len(body["months"]) == 12
    for i, m in enumerate(body["months"]):
        month_num = i + 1
        assert m["active"] == (month_num >= 4)
        if month_num < 4:
            assert m["amount"] == 0.0
        else:
            assert m["amount"] == 10_000.0
    # Golden value for the first active month (April), no PPK.
    april = body["months"][3]
    assert april["breakdown"]["net"] == 7147.39
    assert april["employer_cost"] == 12048.0


def test_entry_override_changes_month_and_ytd(client):
    src = _create_uop_source(client)
    r = client.put(f"/api/income/sources/{src['id']}/entries/2026-03", json={"amount": 15_000})
    assert r.status_code == 200

    body = client.get(f"/api/income/sources/{src['id']}/year/2026").json()
    march = body["months"][2]
    assert march["amount"] == 15_000.0
    assert march["breakdown"]["gross"] == 15_000.0

    # The YTD maths of later months must match running the engine directly
    # on the same gross sequence (Jan/Feb 10k, Mar 15k, rest 10k).
    opts = UopOptions(ppk_employee=0, ppk_employer=0)
    expected = uop_schedule(2026, [10_000, 10_000, 15_000] + [10_000] * 9, opts)
    for i in range(3, 12):
        assert body["months"][i]["breakdown"]["pit_base"] == expected.months[i].pit_base
        assert body["months"][i]["breakdown"]["net"] == expected.months[i].net


def test_override_net_wins_over_engine_net(client):
    src = _create_uop_source(client)
    r = client.put(
        f"/api/income/sources/{src['id']}/entries/2026-05",
        json={"amount": 10_000, "override_net": 6_000},
    )
    assert r.status_code == 200
    assert r.json()["override_net"] == 6_000.0

    body = client.get(f"/api/income/sources/{src['id']}/year/2026").json()
    may = body["months"][4]
    assert may["overridden"] is True
    assert may["net_pln"] == 6_000.0
    assert may["net_in_base"] == 6_000.0
    # The engine still saw the full 10k gross for its own YTD maths.
    assert may["breakdown"]["gross"] == 10_000.0
    assert may["breakdown"]["net"] != 6_000.0


def test_delete_source_removes_entries(client, db):
    from sqlalchemy import func

    from src.models.income import IncomeEntry

    src = _create_uop_source(client)
    client.put(f"/api/income/sources/{src['id']}/entries/2026-03", json={"amount": 15_000})
    assert db.query(func.count(IncomeEntry.id)).filter(IncomeEntry.source_id == src["id"]).scalar() == 1

    r = client.delete(f"/api/income/sources/{src['id']}")
    assert r.status_code == 204
    assert db.query(func.count(IncomeEntry.id)).filter(IncomeEntry.source_id == src["id"]).scalar() == 0
    assert client.get(f"/api/income/sources/{src['id']}/year/2026").status_code == 404


def test_b2b_eur_source_converts_at_fallback_rate(client):
    r = client.post(
        "/api/income/sources",
        json={
            "name": "Freelance EUR",
            "kind": "b2b",
            "currency": "EUR",
            "params": {
                "billing": "monthly",
                "invoice_monthly": 1_000,
                "costs_monthly": 0,
                "tax_form": "liniowy",
                "zus_stage": "full",
            },
            "starts_on": "2026-01-01",
        },
    )
    assert r.status_code == 201
    src = r.json()

    body = client.get(f"/api/income/sources/{src['id']}/year/2026").json()
    jan = body["months"][0]
    assert jan["amount"] == 1_000.0
    # Offline fallbacks: 1 USD = 3.95 PLN = 0.92 EUR, so EUR->PLN is 3.95/0.92.
    expected_pln = round(1_000 * (3.95 / 0.92), 2)
    assert jan["breakdown"]["revenue"] == expected_pln


def test_other_kind_has_no_tax_maths(client):
    r = client.post(
        "/api/income/sources",
        json={
            "name": "Rental",
            "kind": "other",
            "currency": "PLN",
            "params": {"net_monthly": 2_000},
            "starts_on": "2026-01-01",
        },
    )
    assert r.status_code == 201
    src = r.json()
    body = client.get(f"/api/income/sources/{src['id']}/year/2026").json()
    jan = body["months"][0]
    assert jan["breakdown"] is None
    assert jan["net_pln"] == 2_000.0
    assert jan["net_in_base"] == 2_000.0


def test_invalid_params_for_kind_is_422(client):
    r = client.post(
        "/api/income/sources",
        json={
            "name": "Bad",
            "kind": "uop",
            "currency": "PLN",
            "params": {"gross_monthly": -5},  # negative -> invalid
            "starts_on": "2026-01-01",
        },
    )
    assert r.status_code == 422


def test_list_sources_includes_year_summary_and_current_month(client, monkeypatch):
    from datetime import date

    monkeypatch.setattr("src.routes.income.today_in", lambda db: date(2026, 6, 15))
    _create_uop_source(client)
    r = client.get("/api/income/sources")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["current_month"]["month"] == "2026-06"
    assert "totals" in body[0]["year_summary"] or "annual_pit" in body[0]["year_summary"]


def test_delete_entry_404_when_missing(client):
    src = _create_uop_source(client)
    r = client.delete(f"/api/income/sources/{src['id']}/entries/2026-03")
    assert r.status_code == 404
