"""GET /api/positions/growth: your money vs. growth, per asset and in total.

Offline prices (see conftest.py): 1 USD = 3.95 PLN, BTC 65000 USD. Base
currency defaults to PLN.
"""
import pytest


def _create_asset(client, **overrides):
    payload = {"name": "Test asset", "kind": "currency", "units": ""}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _growth(client):
    r = client.get("/api/positions/growth")
    assert r.status_code == 200, r.text
    return r.json()


def test_currency_deposit_counts_as_your_money_not_growth(client):
    """1000 -> 1120 with a 100 flow: 20 of the 120 rise is growth, 100 is
    the user's own deposit."""
    asset = _create_asset(client, name="Brokerage", kind="currency")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"}
    )
    assert created.status_code == 201, created.text
    pos = created.json()
    client.put(
        f"/api/positions/{pos['id']}",
        json={"amount": 1120, "currency": "PLN", "flow": 100},
    )

    body = _growth(client)
    assert len(body["assets"]) == 1
    row = body["assets"][0]
    assert row["asset_id"] == asset["id"]
    assert row["invested"] == pytest.approx(1100.0)
    assert row["growth"] == pytest.approx(20.0)
    assert row["untracked_updates"] == 0
    assert row["last"]["change"] == pytest.approx(120.0)
    assert row["last"]["flow"] == pytest.approx(100.0)
    assert row["last"]["growth"] == pytest.approx(20.0)


def test_blank_flow_is_untracked_and_all_change_is_growth(client):
    """1000 -> 1050 with no flow entered: the whole 50 rise counts as
    growth, and the update is flagged as untracked."""
    asset = _create_asset(client, name="Savings", kind="currency")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"}
    )
    pos = created.json()
    client.put(f"/api/positions/{pos['id']}", json={"amount": 1050, "currency": "PLN"})

    row = _growth(client)["assets"][0]
    assert row["contributed"] == pytest.approx(0.0)
    assert row["growth"] == pytest.approx(50.0)
    assert row["untracked_updates"] == 1
    assert row["last"]["flow"] is None
    assert row["last"]["growth"] == pytest.approx(50.0)


def test_withdrawal_reduces_invested(client):
    """1000 -> 700 with a -400 flow (a withdrawal larger than the drop in
    value): invested drops to 600, so the 700 left is actually up on that."""
    asset = _create_asset(client, name="Brokerage", kind="currency")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"}
    )
    pos = created.json()
    client.put(
        f"/api/positions/{pos['id']}",
        json={"amount": 700, "currency": "PLN", "flow": -400},
    )

    row = _growth(client)["assets"][0]
    assert row["invested"] == pytest.approx(600.0)
    assert row["growth"] == pytest.approx(100.0)


def test_single_snapshot_has_zero_growth_and_no_last(client):
    asset = _create_asset(client, name="Cash", kind="currency")
    client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 500, "currency": "PLN"}
    )

    row = _growth(client)["assets"][0]
    assert row["growth"] == pytest.approx(0.0)
    assert row["last"] is None


def test_no_positions_gives_empty_assets_and_zero_totals(client):
    body = _growth(client)
    assert body["assets"] == []
    assert body["total"]["opening_value"] == 0
    assert body["total"]["contributed"] == 0
    assert body["total"]["invested"] == 0
    assert body["total"]["value"] == 0
    assert body["total"]["growth"] == 0
    assert body["total"]["untracked_updates"] == 0
    assert body["total"]["growth_pct"] is None


def test_totals_sum_across_two_assets(client):
    a1 = _create_asset(client, name="Brokerage", kind="currency")
    a2 = _create_asset(client, name="Savings", kind="currency")
    p1 = client.post(
        "/api/positions", json={"asset_id": a1["id"], "amount": 1000, "currency": "PLN"}
    ).json()
    client.put(
        f"/api/positions/{p1['id']}",
        json={"amount": 1120, "currency": "PLN", "flow": 100},
    )
    client.post(
        "/api/positions", json={"asset_id": a2["id"], "amount": 500, "currency": "PLN"}
    )

    total = _growth(client)["total"]
    assert total["invested"] == pytest.approx(1100.0 + 500.0)
    assert total["value"] == pytest.approx(1120.0 + 500.0)
    assert total["growth"] == pytest.approx(20.0 + 0.0)
    assert total["growth_pct"] == pytest.approx(total["growth"] / total["invested"])


def test_crypto_quantity_increase_with_no_flow_derives_flow_and_excludes_it(client):
    """Quantity goes up with no flow typed: the value moves purely because
    of the added quantity (price is unchanged, offline), so once the
    derived flow is backed out, growth is 0."""
    asset = _create_asset(client, name="Bitcoin", kind="crypto", units="BTC")
    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1, "currency": "PLN"}
    )
    pos = created.json()
    client.put(f"/api/positions/{pos['id']}", json={"amount": 1.5, "currency": "PLN"})

    row = _growth(client)["assets"][0]
    assert row["untracked_updates"] == 0  # derived server-side, not blank
    assert row["growth"] == pytest.approx(0.0)
    assert row["last"]["flow"] is not None
