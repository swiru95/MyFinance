"""GET/PUT /api/fire/settings and the assembled GET /api/fire.

Base currency defaults to PLN, so every asset amount below is already in
base currency and no FX conversion enters the expected figures.
"""
import pytest


def _asset(client, **overrides):
    payload = {"name": "asset", "kind": "currency"}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _position(client, asset_id, amount):
    r = client.post("/api/positions", json={"asset_id": asset_id, "amount": amount, "currency": "PLN"})
    assert r.status_code == 201, r.text
    return r.json()


def _expense(client, amount, category=""):
    r = client.post(
        "/api/expenses",
        json={
            "name": "Rent",
            "amount": amount,
            "currency": "PLN",
            "period": "monthly",
            "category": category,
            "starts_on": "2024-01-01",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_settings_default_before_anything_is_saved(client):
    body = client.get("/api/fire/settings").json()
    assert body["birth_year"] is None
    assert body["retirement_age"] == 65
    assert body["swr"] == 0.035
    assert body["emergency_months"] == 6


def test_settings_round_trip(client):
    payload = {
        "birth_year": 1990,
        "target_fi_age": 45,
        "retirement_age": 65,
        "swr": 0.04,
        "inflation": 0.03,
        "real_return_override": 0.05,
        "monthly_spend_override": 6000,
        "barista_income_monthly": 2000,
        "zus_pension_monthly": 3000,
        "include_health_cost": False,
        "gain_share": 0.6,
        "emergency_months": 9,
        "lean_factor": 0.7,
        "fat_factor": 1.6,
    }
    put = client.put("/api/fire/settings", json=payload)
    assert put.status_code == 200, put.text
    got = client.get("/api/fire/settings").json()
    for key, value in payload.items():
        assert got[key] == value, key


def test_settings_validation_rejects_out_of_range_swr(client):
    r = client.put("/api/fire/settings", json={"swr": 0.5})
    assert r.status_code == 422


def test_settings_validation_rejects_birth_year_in_the_future(client):
    r = client.put("/api/fire/settings", json={"birth_year": 3000})
    assert r.status_code == 422


def test_fire_without_birth_year_returns_needs(client):
    r = client.get("/api/fire")
    assert r.status_code == 200
    body = r.json()
    assert body["needs"] == ["birth_year"]
    assert body["result"] is None
    assert "settings" in body


def test_fire_assembles_reserve_wrapper_and_illiquid_exclusion(client):
    cash = _asset(client, name="Cash", category="Cash", profile="safe")
    _position(client, cash["id"], 100_000)

    stock = _asset(client, name="Broker", category="Stocks", wrapper="ike")
    _position(client, stock["id"], 50_000)

    watch = _asset(client, name="Watch", category="Watches")  # profile falls back to illiquid
    _position(client, watch["id"], 20_000)

    _expense(client, 5000)

    client.put("/api/fire/settings", json={"birth_year": 1990})

    r = client.get("/api/fire")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["inputs"]["excluded_illiquid"] == pytest.approx(20_000)
    assert body["inputs"]["reserve"] == pytest.approx(30_000)  # 6 months x 5000
    assert body["inputs"]["accessible_assets"] == pytest.approx(70_000)  # 100000 - 30000
    assert body["inputs"]["wrapped_assets"] == pytest.approx(50_000)
    assert body["inputs"]["spend_source"] == "committed"
    assert body["result"]["targets"]["regular"] > 0
    assert body["required_income"] is None  # no target_fi_age set
    assert body["disclaimer_key"] == "fire.disclaimer"


def test_fire_oki_wrapper_counts_as_accessible_not_wrapped(client):
    # OKI is tax-advantaged but carries no age lock (unlike IKE/IKZE/PPK/OIPE),
    # so it belongs in accessible_assets, not wrapped_assets - the inverse of
    # what an IKE-wrapped holding of the same size does.
    cash = _asset(client, name="Cash", category="Cash", profile="safe")
    _position(client, cash["id"], 100_000)

    oki = _asset(client, name="OKI broker", category="Stocks", wrapper="oki")
    _position(client, oki["id"], 50_000)

    ike = _asset(client, name="IKE broker", category="Stocks", wrapper="ike")
    _position(client, ike["id"], 50_000)

    _expense(client, 5000)
    client.put("/api/fire/settings", json={"birth_year": 1990})

    body = client.get("/api/fire").json()
    # 100_000 (cash) + 50_000 (oki) - 30_000 (reserve, 6 x 5000) = 120_000.
    assert body["inputs"]["accessible_assets"] == pytest.approx(120_000)
    assert body["inputs"]["wrapped_assets"] == pytest.approx(50_000)  # only the IKE leg


def test_fire_reserve_floors_accessible_at_zero(client):
    cash = _asset(client, name="Small cash", category="Cash", profile="safe")
    _position(client, cash["id"], 1000)  # far less than the reserve
    _expense(client, 5000)
    client.put("/api/fire/settings", json={"birth_year": 1990})

    body = client.get("/api/fire").json()
    assert body["inputs"]["accessible_assets"] == 0.0


def test_fire_required_income_present_when_target_fi_age_set(client):
    cash = _asset(client, name="Cash", category="Cash", profile="safe")
    _position(client, cash["id"], 500_000)
    _expense(client, 5000)
    client.put("/api/fire/settings", json={"birth_year": 1990, "target_fi_age": 45})

    body = client.get("/api/fire").json()
    assert body["required_income"] is not None
    for key in ("uop", "b2b_skala", "b2b_liniowy", "b2b_ryczalt"):
        assert key in body["required_income"]
        assert "gross_monthly" in body["required_income"][key] or "revenue_monthly" in body["required_income"][key]


def test_required_income_uses_the_users_own_b2b_terms(client):
    """Regression: the reverse calculation must read the active B2B source,
    not silently fall back to engine defaults."""
    from src.tax.pl.b2b import B2bOptions
    from src.tax.pl.reverse import reverse_b2b

    client.post("/api/income/sources", json={
        "name": "JDG", "kind": "b2b", "starts_on": "2020-01-01",
        "params": {"billing": "monthly", "invoice_monthly": 15000,
                   "costs_monthly": 800, "tax_form": "ryczalt",
                   "zus_stage": "preferential", "sickness": True},
    })
    _expense(client, 5000)
    client.put("/api/fire/settings", json={"birth_year": 1992, "target_fi_age": 50})
    body = client.get("/api/fire").json()

    target = body["result"]["required"]["required_net_income"]
    year = body["inputs"]["params_year"]
    expected = reverse_b2b(year, target, 800, B2bOptions(
        tax_form="liniowy", zus_stage="preferential", sickness=True))
    got = body["required_income"]["b2b_liniowy"]
    assert got["revenue_monthly"] == pytest.approx(expected["revenue_monthly"], abs=1)


def test_committed_spend_source_excludes_business_contributions(client):
    """The monthly_spend "committed" fallback must read monthly_total_personal,
    not monthly_total - a B2B source's fixed ZUS/health contributions stop
    once the JDG is closed at FI, so they should not inflate the pre-FI
    spend estimate either (see routes/fire.get_fire)."""
    client.post("/api/income/sources", json={
        "name": "JDG", "kind": "b2b", "starts_on": "2020-01-01",
        "params": {"billing": "monthly", "invoice_monthly": 15000,
                   "costs_monthly": 0, "tax_form": "liniowy",
                   "zus_stage": "full", "sickness": True},
    })
    _expense(client, 5000)
    client.put("/api/fire/settings", json={"birth_year": 1990})

    summary = client.get("/api/expenses/summary").json()
    assert summary["business_contributions_total"] == pytest.approx(2359.30)
    assert summary["monthly_total"] == pytest.approx(5000 + 2359.30)

    body = client.get("/api/fire").json()
    assert body["inputs"]["spend_source"] == "committed"
    # Personal-only (5000), not the full monthly_total (7359.30).
    assert body["inputs"]["monthly_spend"] == pytest.approx(5000)
