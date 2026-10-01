"""kind="metal" (silver/platinum/palladium) and the new crypto coins
(ETH/XRP/BNB), plus the catalogue endpoint.

Offline prices (see conftest.py's offline_prices fixture, which now also
covers _fetch_metal_usd_per_oz): 1 USD = 3.95 PLN, XAU 2650 USD/oz, XAG 31
USD/oz, XPT/XPD 1000 USD/oz, BTC 65000 / ETH 3500 / SOL 150 / XRP 0.6 /
BNB 600 USD.
"""
import pytest

_OZ_TO_GRAM = 31.1034768
_USD_PLN = 3.95


def _create_asset(client, **overrides):
    payload = {"name": "Test asset", "kind": "currency", "units": ""}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    return r


def test_silver_position_value(client):
    """100 g XAG = 100 x 31 / 31.1034768 x PLN-per-USD."""
    asset = _create_asset(
        client, name="Silver", kind="metal", units="XAG", category="Metals"
    ).json()

    pos = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 100, "currency": "PLN"}
    )
    assert pos.status_code == 201, pos.text
    body = pos.json()

    expected_price = (31.0 / _OZ_TO_GRAM) * _USD_PLN
    expected_value = 100 * expected_price
    assert body["price_used"] == pytest.approx(expected_price, rel=1e-4)
    assert body["value_in_base"] == pytest.approx(expected_value, rel=1e-4)


def test_platinum_and_palladium_also_price(client):
    for symbol in ("XPT", "XPD"):
        asset = _create_asset(
            client, name=symbol, kind="metal", units=symbol, category="Metals"
        ).json()
        pos = client.post(
            "/api/positions", json={"asset_id": asset["id"], "amount": 10, "currency": "PLN"}
        )
        assert pos.status_code == 201, pos.text
        expected_price = (1000.0 / _OZ_TO_GRAM) * _USD_PLN
        assert pos.json()["price_used"] == pytest.approx(expected_price, rel=1e-4)


def test_ethereum_position_value(client):
    """0.5 ETH."""
    asset = _create_asset(
        client, name="Ethereum", kind="crypto", units="ETH", category="Crypto"
    ).json()

    pos = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 0.5, "currency": "PLN"}
    )
    assert pos.status_code == 201, pos.text
    body = pos.json()

    expected_price = 3500.0 * _USD_PLN
    assert body["price_used"] == pytest.approx(expected_price, rel=1e-4)
    assert body["value_in_base"] == pytest.approx(0.5 * expected_price, rel=1e-4)


def test_invalid_crypto_units_rejected(client):
    r = _create_asset(client, name="Dogecoin", kind="crypto", units="DOGE")
    assert r.status_code == 422, r.text


def test_invalid_metal_units_rejected(client):
    r = _create_asset(client, name="Copper", kind="metal", units="XCU")
    assert r.status_code == 422, r.text


def test_valid_crypto_units_accepted(client):
    for symbol in ("BTC", "ETH", "SOL", "XRP", "BNB"):
        r = _create_asset(client, name=symbol, kind="crypto", units=symbol)
        assert r.status_code == 201, r.text


def test_existing_gold_kind_asset_still_values_the_same(client):
    """kind="gold" is untouched by the metal generalisation: always XAU,
    ignoring its own `units` field (the default asset types set it to "g", a label,
    not a symbol)."""
    asset = _create_asset(client, name="Gold Bar", kind="gold", units="g").json()
    pos = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 10, "currency": "PLN"}
    )
    assert pos.status_code == 201, pos.text
    expected_price = (2650.0 / _OZ_TO_GRAM) * _USD_PLN
    assert pos.json()["price_used"] == pytest.approx(expected_price, rel=1e-4)


def test_metal_flow_derived_from_quantity_change(client):
    """Like gold, a metal position's flow is derived from the amount change
    at today's price when no explicit flow is given (see
    routes/positions._flow_in_base, extended to include kind="metal")."""
    asset = _create_asset(client, name="Silver", kind="metal", units="XAG").json()

    created = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 50, "currency": "PLN"}
    )
    assert created.status_code == 201
    pos = created.json()
    assert pos["flow_in_base"] is None  # opening balance, not a flow

    updated = client.put(
        f"/api/positions/{pos['id']}", json={"amount": 80, "currency": "PLN"}
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    price_used = body["price_used"]
    assert body["flow_in_base"] == pytest.approx(30 * price_used, rel=1e-4)


def test_catalogue_lists_four_metals_and_five_coins(client):
    r = client.get("/api/prices/catalogue")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {e["symbol"] for e in body["metals"]} == {"XAU", "XAG", "XPT", "XPD"}
    assert {e["symbol"] for e in body["crypto"]} == {"BTC", "ETH", "SOL", "XRP", "BNB"}
    # Every entry carries both languages and the bits AssetForm needs.
    for entry in body["metals"] + body["crypto"]:
        assert entry["name"]["en"] and entry["name"]["pl"]
        assert entry["icon"]
        assert entry["category"]
        assert entry["profile"]
        assert entry["unit"] in ("g", "coin")


def test_prices_endpoint_reports_held_metals_and_coins(client):
    silver = _create_asset(client, name="Silver", kind="metal", units="XAG").json()
    eth = _create_asset(client, name="Ethereum", kind="crypto", units="ETH").json()
    client.post("/api/positions", json={"asset_id": silver["id"], "amount": 10, "currency": "PLN"})
    client.post("/api/positions", json={"asset_id": eth["id"], "amount": 1, "currency": "PLN"})

    r = client.get("/api/prices")
    assert r.status_code == 200, r.text
    body = r.json()
    # Backward-compat fields still present.
    assert "gold_per_gram" in body
    assert {"BTC", "SOL"} <= set(body["crypto"])
    # New: the held metal/coin are reported too.
    assert "XAG" in body["metals"]
    assert "ETH" in body["crypto"]
    assert "XAU" in body["metals"]  # backward compat


def test_summary_endpoint_reports_metals(client):
    silver = _create_asset(client, name="Silver", kind="metal", units="XAG").json()
    client.post("/api/positions", json={"asset_id": silver["id"], "amount": 10, "currency": "PLN"})

    r = client.get("/api/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "metals" in body
    assert "XAG" in body["metals"]
    assert "XAU" in body["metals"]
    assert "gold_price" in body  # backward compat
    assert "crypto_prices" in body  # backward compat
