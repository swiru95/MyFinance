"""services/business_costs.fixed_contributions and its surfacing through
GET /api/expenses/summary.

Figures pinned here are hand-verified against tax/pl/b2b.jdg_social_monthly
and TaxYear.health_min_monthly for 2026 (see 00-architecture.md's verified
parameter table): full ZUS + sickness = 1 926.76, health minimum = 432.54,
preferential ZUS (no sickness) = 420.86, ryczałt tier 3 = 1 495.04.
"""


def _b2b_source(client, **overrides):
    payload = {
        "name": "JDG",
        "kind": "b2b",
        "currency": "PLN",
        "params": {
            "billing": "monthly",
            "invoice_monthly": 15_000,
            "costs_monthly": 0,
            "tax_form": "liniowy",
            "zus_stage": "full",
            "sickness": True,
        },
        "starts_on": "2024-01-01",
    }
    payload.update(overrides)
    r = client.post("/api/income/sources", json=payload)
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


def test_no_b2b_source_gives_empty_contributions_and_equal_totals(client):
    _expense(client, 2000)
    body = client.get("/api/expenses/summary").json()
    assert body["business_contributions"] == []
    assert body["business_contributions_total"] == 0
    assert body["monthly_total"] == body["monthly_total_personal"] == 2000


def test_full_zus_with_sickness_liniowy_source(client):
    """Liniowy, full ZUS stage, voluntary sickness on: social 1 926.76 +
    health minimum 432.54 = 2 359.30, and it lands on top of typed spend."""
    _expense(client, 3000)
    src = _b2b_source(client)

    body = client.get("/api/expenses/summary").json()
    assert len(body["business_contributions"]) == 1
    row = body["business_contributions"][0]
    assert row["source_id"] == src["id"]
    assert row["social"] == 1926.76
    assert row["health_fixed"] == 432.54
    assert row["total"] == 2359.30
    assert row["currency"] == body["base_currency"]

    assert body["business_contributions_total"] == 2359.30
    assert body["monthly_total_personal"] == 3000
    assert body["monthly_total"] == 3000 + 2359.30

    # The breakdown adds up: typed categories plus the business-contribution
    # bucket sum to monthly_total.
    assert sum(c["total"] for c in body["by_category"]) == body["monthly_total"]


def test_preferential_zus_without_sickness(client):
    """Preferential base, sickness off: social 420.86 (pension+disability+
    accident only - no FP on the preferential base, no sickness)."""
    _b2b_source(client, params={
        "billing": "monthly", "invoice_monthly": 8000, "costs_monthly": 0,
        "tax_form": "liniowy", "zus_stage": "preferential", "sickness": False,
    })
    body = client.get("/api/expenses/summary").json()
    row = body["business_contributions"][0]
    assert row["social"] == 420.86


def test_ryczalt_with_pinned_health_tier(client):
    """A chosen ryczałt tier is what is actually paid every month,
    regardless of what the year's revenue would otherwise imply."""
    _b2b_source(client, params={
        "billing": "monthly", "invoice_monthly": 3000, "costs_monthly": 0,
        "tax_form": "ryczalt", "ryczalt_rate": 0.12, "zus_stage": "full",
        "ryczalt_health_tier": 3,
    })
    body = client.get("/api/expenses/summary").json()
    row = body["business_contributions"][0]
    assert row["health_fixed"] == 1495.04


def test_inactive_source_contributes_nothing(client):
    _b2b_source(client, starts_on="2020-01-01", ends_on="2020-12-31")
    body = client.get("/api/expenses/summary").json()
    assert body["business_contributions"] == []
    assert body["business_contributions_total"] == 0


def test_monthly_committed_stays_personal_only(client):
    """Regression: the monthly budget's committed figure must never pick up
    JDG contributions - see routes/monthly.committed_for_month, which only
    ever walks typed Expense rows."""
    _expense(client, 1000)
    _b2b_source(client)  # would add 2359.30 if it leaked into committed

    # today_in needs a db session; hit the API instead, which threads one.
    month = client.get("/api/monthly").json()[0]["month"]
    body = client.get(f"/api/monthly/{month}").json()
    assert body["committed"] == 1000
