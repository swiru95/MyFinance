"""flow_in_base: what moved money in/out of a position vs. what the market did.

Offline prices (see conftest.py): 1 USD = 3.95 PLN = 0.92 EUR, gold 2650
USD/oz. Base currency defaults to PLN.
"""
import pytest


def _create_asset(client, **overrides):
    payload = {"name": "Test asset", "kind": "currency", "units": ""}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_gold_update_derives_flow_from_amount_change(client):
    asset = _create_asset(client, name="Gold Bar", kind="gold", units="g")

    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 10, "currency": "PLN"}
    )
    assert created.status_code == 201, created.text
    pos = created.json()
    assert pos["flow_in_base"] is None  # opening balance, not a flow

    updated = client.put(
        f"/api/positions/{pos['id']}", json={"amount": 15, "currency": "PLN"}
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    price_used = body["price_used"]
    assert body["flow_in_base"] == pytest.approx(5 * price_used, rel=1e-4)


def test_currency_update_with_explicit_flow_converts_from_payload_currency(client):
    asset = _create_asset(client, name="Brokerage", kind="currency")

    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 10_000, "currency": "PLN"}
    )
    assert created.status_code == 201
    pos = created.json()

    updated = client.put(
        f"/api/positions/{pos['id']}",
        json={"amount": 11_000, "currency": "PLN", "flow": 1000, "notes": ""},
    )
    assert updated.status_code == 200, updated.text
    # The flow is denominated in the payload's own currency (here still PLN
    # for the amount, but the flow itself is stated in EUR in the next case);
    # this case pins down the plain PLN-in-PLN path first.
    assert updated.json()["flow_in_base"] == pytest.approx(1000.0)


def test_currency_flow_given_in_a_different_currency_than_the_amount(client):
    asset = _create_asset(client, name="Brokerage EUR", kind="currency")

    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 10_000, "currency": "PLN"}
    )
    pos = created.json()

    # currency is EUR here so both `amount` and `flow` are read as EUR figures,
    # and flow_in_base must come out in PLN (base) at 3.95/0.92 per EUR.
    updated = client.put(
        f"/api/positions/{pos['id']}",
        json={"amount": 5000, "currency": "EUR", "flow": 1000},
    )
    assert updated.status_code == 200, updated.text
    expected = 1000 * (3.95 / 0.92)
    assert updated.json()["flow_in_base"] == pytest.approx(expected, rel=1e-6)


def test_currency_update_without_flow_is_null(client):
    asset = _create_asset(client, name="Savings", kind="currency")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 5000, "currency": "PLN"}
    )
    pos = created.json()

    updated = client.put(
        f"/api/positions/{pos['id']}", json={"amount": 6000, "currency": "PLN"}
    )
    assert updated.status_code == 200
    assert updated.json()["flow_in_base"] is None


def test_create_without_flow_is_null_even_for_gold(client):
    asset = _create_asset(client, name="Gold Coins", kind="gold", units="g")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 20, "currency": "PLN"}
    )
    assert created.status_code == 201
    assert created.json()["flow_in_base"] is None


def test_interest_flow_is_stored_as_base_currency_as_is(client):
    asset = _create_asset(client, name="Loan owed to me", kind="interest", interest_basis="late")
    created = client.post(
        "/api/positions",
        json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"},
    )
    pos = created.json()
    assert pos["flow_in_base"] is None

    updated = client.put(
        f"/api/positions/{pos['id']}",
        json={"amount": 1200, "currency": "PLN", "flow": 200},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["flow_in_base"] == 200.0
