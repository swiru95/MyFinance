"""PATCH /api/monthly/{month}: partial updates to a row two pages share.

Expenses saves actual_spent/notes, Income saves income/currency, and neither
may know the other's current figure - so PATCH must touch only the fields it
receives, never defaulting the rest back to zero/blank like a PUT would.
"""


def test_patch_actual_spent_keeps_previously_set_income(client):
    client.put("/api/monthly/2026-03", json={"income": 8000, "actual_spent": 100, "currency": "PLN"})

    r = client.patch("/api/monthly/2026-03", json={"actual_spent": 4500})
    assert r.status_code == 200
    body = r.json()
    assert body["income"] == 8000.0
    assert body["actual_spent"] == 4500.0
    assert body["currency"] == "PLN"


def test_patch_income_keeps_previously_set_actual_spent(client):
    client.put("/api/monthly/2026-03", json={"income": 8000, "actual_spent": 4500, "currency": "PLN"})

    r = client.patch("/api/monthly/2026-03", json={"income": 8200})
    assert r.status_code == 200
    body = r.json()
    assert body["income"] == 8200.0
    assert body["actual_spent"] == 4500.0


def test_patch_on_missing_month_creates_it(client):
    r = client.patch("/api/monthly/2026-07", json={"actual_spent": 1200})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True
    assert body["actual_spent"] == 1200.0
    # Unset numbers default to 0 and currency to the base currency, not left null.
    assert body["income"] == 0.0
    assert body["currency"] == "PLN"

    # And it persists - a second read finds the created row, not a fresh default.
    r2 = client.get("/api/monthly/2026-07")
    assert r2.json()["actual_spent"] == 1200.0


def test_patch_empty_body_is_a_no_op_create(client):
    r = client.patch("/api/monthly/2026-08", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True
    assert body["income"] == 0.0
    assert body["actual_spent"] == 0.0


def test_patch_invalid_month_is_422(client):
    r = client.patch("/api/monthly/2026-13", json={"actual_spent": 100})
    assert r.status_code == 422

    r2 = client.patch("/api/monthly/not-a-month", json={"actual_spent": 100})
    assert r2.status_code == 422
