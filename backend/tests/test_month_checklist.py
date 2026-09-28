"""The "month checklist" (WP-M): GET .../commitments plus the derived
actual_spent that PUT/PATCH now compute from a checklist + "everything else"
figure instead of taking one typed total.
"""
from src.routes.helpers import convert_currency
from src.services.price_service import PriceService


def _expense(client, name, amount, *, currency="PLN", period="monthly",
             starts_on="2026-01-01", ends_on=None, category=""):
    r = client.post("/api/expenses", json={
        "name": name,
        "amount": amount,
        "currency": currency,
        "period": period,
        "category": category,
        "starts_on": starts_on,
        "ends_on": ends_on,
        "notes": "",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_commitments_default_to_paid_and_put_computes_actual_spent(client):
    rent = _expense(client, "Rent", 100)
    gym = _expense(client, "Gym", 50)

    rows = client.get("/api/monthly/2026-03/commitments").json()
    assert {r["expense_id"] for r in rows} == {rent["id"], gym["id"]}
    assert all(r["paid"] is True for r in rows)
    assert all(r["currency"] == "PLN" for r in rows)

    r = client.put("/api/monthly/2026-03", json={
        "income": 0,
        "actual_spent": 0,
        "currency": "PLN",
        "notes": "",
        "commitments": [
            {"expense_id": rent["id"], "amount": 100, "paid": True},
            {"expense_id": gym["id"], "amount": 50, "paid": True},
        ],
        "other_spent": 400,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["actual_spent"] == 550.0
    assert body["breakdown"] is True
    assert body["commitments_paid_total"] == 150.0
    assert body["other_spent"] == 400.0


def test_unticking_a_commitment_lowers_actual_spent_and_shows_unpaid(client):
    rent = _expense(client, "Rent", 100)
    gym = _expense(client, "Gym", 50)
    client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [
            {"expense_id": rent["id"], "amount": 100, "paid": True},
            {"expense_id": gym["id"], "amount": 50, "paid": True},
        ],
        "other_spent": 400,
    })

    r = client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [
            {"expense_id": rent["id"], "amount": 100, "paid": True},
            {"expense_id": gym["id"], "amount": 50, "paid": False},
        ],
        "other_spent": 400,
    })
    assert r.status_code == 200
    assert r.json()["actual_spent"] == 500.0

    rows = client.get("/api/monthly/2026-03/commitments").json()
    gym_row = next(row for row in rows if row["expense_id"] == gym["id"])
    assert gym_row["paid"] is False
    rent_row = next(row for row in rows if row["expense_id"] == rent["id"])
    assert rent_row["paid"] is True


def test_commitment_currency_converts_to_record_currency(client):
    """A commitment's amount is in the expense's own currency; the derived
    actual_spent and commitments_paid_total convert it into the record's
    currency with the same offline fallback FX rate the rest of the app
    uses - computed here rather than hard-coded, so the test does not rot
    if the fallback table is ever updated."""
    netflix = _expense(client, "Netflix EU", 10, currency="EUR")

    r = client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [{"expense_id": netflix["id"], "amount": 10, "paid": True}],
        "other_spent": 0,
    })
    assert r.status_code == 200

    ps = PriceService("PLN")
    expected = round(convert_currency(ps, 10.0, "EUR", "PLN"), 2)
    body = r.json()
    assert body["actual_spent"] == expected
    assert body["commitments_paid_total"] == expected


def test_yearly_expense_only_appears_in_its_charge_month(client):
    _expense(client, "Car insurance", 1200, period="yearly", starts_on="2026-03-15")

    charge_month = client.get("/api/monthly/2026-03/commitments").json()
    assert len(charge_month) == 1
    assert charge_month[0]["name"] == "Car insurance"

    other_month = client.get("/api/monthly/2026-04/commitments").json()
    assert other_month == []


def test_legacy_put_with_actual_spent_only_keeps_working_as_before(client):
    r = client.put("/api/monthly/2026-03", json={
        "income": 1000, "actual_spent": 4200, "currency": "PLN", "notes": "legacy",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["actual_spent"] == 4200.0
    assert body["breakdown"] is False
    assert body["commitments_paid_total"] is None
    assert body["other_spent"] is None


def test_unknown_expense_id_in_commitments_is_422(client):
    r = client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [{"expense_id": 999999, "amount": 10, "paid": True}],
        "other_spent": 0,
    })
    assert r.status_code == 422

    # And nothing was written - the month was not silently half-saved.
    r2 = client.get("/api/monthly/2026-03")
    assert r2.json()["saved"] is False


def test_legacy_write_onto_breakdown_record_clears_breakdown(client):
    """Breakdown PUT, then legacy PATCH {actual_spent: 999} → breakdown false,
    actual_spent 999, commitments_paid and other_spent null."""
    rent = _expense(client, "Rent", 100)

    # First, save a breakdown.
    r = client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [{"expense_id": rent["id"], "amount": 100, "paid": True}],
        "other_spent": 200,
    })
    assert r.status_code == 200
    assert r.json()["breakdown"] is True

    # Then, write a legacy actual_spent value.
    r = client.patch("/api/monthly/2026-03", json={"actual_spent": 999})
    assert r.status_code == 200
    body = r.json()
    assert body["breakdown"] is False
    assert body["actual_spent"] == 999.0
    assert body["commitments_paid_total"] is None
    assert body["other_spent"] is None


def test_currency_change_on_breakdown_record_recomputes_actual_spent(client):
    """Breakdown record in PLN with one paid 10 EUR commitment and other_spent 100,
    then PATCH {currency: "EUR"} → actual_spent recomputed in EUR, breakdown stays true."""
    netflix = _expense(client, "Netflix EU", 10, currency="EUR")

    # Save a breakdown in PLN.
    r = client.put("/api/monthly/2026-03", json={
        "income": 0, "actual_spent": 0, "currency": "PLN", "notes": "",
        "commitments": [{"expense_id": netflix["id"], "amount": 10, "paid": True}],
        "other_spent": 100,
    })
    assert r.status_code == 200
    original = r.json()
    assert original["breakdown"] is True
    assert original["currency"] == "PLN"
    # actual_spent should be the EUR commitment converted to PLN plus other_spent in PLN.
    ps = PriceService("PLN")
    expected_original = round(
        convert_currency(ps, 10.0, "EUR", "PLN") + 100, 2
    )
    assert original["actual_spent"] == expected_original

    # Now change currency to EUR without changing the breakdown.
    r = client.patch("/api/monthly/2026-03", json={"currency": "EUR"})
    assert r.status_code == 200
    converted = r.json()
    assert converted["breakdown"] is True
    assert converted["currency"] == "EUR"
    # actual_spent should now be recomputed in EUR: the 10 EUR commitment (paid) stays
    # 10 EUR in the new currency, and other_spent 100 stays as the stored number
    # (now interpreted as 100 EUR in the new currency).
    expected_converted = round(10.0 + 100.0, 2)
    assert converted["actual_spent"] == expected_converted
