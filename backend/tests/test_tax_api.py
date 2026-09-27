"""Tax preview API: the same golden umowa o pracę value tests/tax/test_uop.py
checks directly on the engine, now reached through HTTP, plus the option
validation the route layer adds on top of it.
"""


def test_uop_golden_value_through_http(client):
    r = client.post(
        "/api/tax/uop",
        json={
            "year": 2026,
            "gross_monthly": 10_000,
            "options": {"ppk_employee": 0, "ppk_employer": 0},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["months"][0]["net"] == 7147.39
    assert body["disclaimer_key"] == "tax.disclaimer"


def test_params_health_min_monthly_2026(client):
    r = client.get("/api/tax/params/2026")
    assert r.status_code == 200
    body = r.json()
    assert body["health_min_monthly"] == 432.54
    assert body["params_year"] == 2026
    assert body["disclaimer_key"] == "tax.disclaimer"
    assert set(body["jdg_social"]) == {"start", "preferential", "full"}


def test_reverse_returns_all_three_b2b_forms(client):
    r = client.post(
        "/api/tax/reverse",
        json={"year": 2026, "target_net_monthly": 8_000, "costs_monthly": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert "uop" in body
    assert set(body["b2b"]) == {"skala", "liniowy", "ryczalt"}
    assert body["disclaimer_key"] == "tax.disclaimer"
    for form_result in body["b2b"].values():
        assert form_result["revenue_monthly"] > 0


def test_invalid_tax_form_is_422(client):
    r = client.post(
        "/api/tax/b2b",
        json={
            "year": 2026,
            "revenue_monthly": 10_000,
            "costs_monthly": 0,
            "options": {"tax_form": "invalid"},
        },
    )
    assert r.status_code == 422


def test_maly_zus_plus_without_custom_base_is_422(client):
    r = client.post(
        "/api/tax/b2b",
        json={
            "year": 2026,
            "revenue_monthly": 10_000,
            "costs_monthly": 0,
            "options": {"zus_stage": "maly_zus_plus"},
        },
    )
    assert r.status_code == 422


def test_gross_by_month_wrong_length_is_422(client):
    r = client.post("/api/tax/uop", json={"year": 2026, "gross_by_month": [10_000] * 11})
    assert r.status_code == 422


def test_compare_uop_b2b(client):
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
    body = r.json()
    assert body["disclaimer_key"] == "tax.disclaimer"
    assert body["uop_annual_net"] > 0
    assert body["b2b_annual_take_home"] > 0
