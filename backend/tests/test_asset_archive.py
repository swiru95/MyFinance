"""POST /api/assets/{id}/archive and /unarchive: soft delete.

Archiving writes a closing snapshot (amount/value 0, flow = -(current value))
when the asset's latest snapshot still has a non-zero current value, so the
asset's unrealised growth becomes realised growth rather than vanishing, and
sets Asset.archived_at. Unarchiving just clears archived_at. See
routes/assets.py and the work package spec for the exact semantics.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from src.models.position import Position
from src.services.ladder import build_ladder


def _asset(client, **overrides):
    payload = {"name": "Test asset", "kind": "currency", "category": "Cash", "profile": "safe"}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _position(client, asset_id, amount, **overrides):
    payload = {"asset_id": asset_id, "amount": amount, "currency": "PLN"}
    payload.update(overrides)
    r = client.post("/api/positions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _growth_row(client, asset_id):
    rows = client.get("/api/positions/growth").json()["assets"]
    return next(r for r in rows if r["asset_id"] == asset_id)


# --- 1. currency asset, untouched since opening -----------------------------

def test_archive_currency_asset_writes_closing_snapshot(client):
    asset = _asset(client)
    _position(client, asset["id"], 1000)

    r = client.post(f"/api/assets/{asset['id']}/archive")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["archived_at"] is not None

    latest = client.get("/api/positions").json()
    latest_row = next(p for p in latest if p["asset_id"] == asset["id"])
    assert float(latest_row["amount"]) == 0
    assert float(latest_row["value_in_base"]) == 0
    assert float(latest_row["flow_in_base"]) == -1000

    growth = _growth_row(client, asset["id"])
    assert growth["value"] == 0
    assert growth["invested"] == 0
    assert growth["growth"] == 0
    assert growth["archived"] is True

    total = client.get("/api/summary").json()["total_value"]
    assert total == 0


# --- 2. an asset that grew with no recorded flow ----------------------------

def test_archive_realises_unflowed_growth(client):
    asset = _asset(client)
    pos1 = _position(client, asset["id"], 1000)
    client.put(
        f"/api/positions/{pos1['id']}",
        json={"asset_id": asset["id"], "amount": 1100, "currency": "PLN"},
    )

    r = client.post(f"/api/assets/{asset['id']}/archive")
    assert r.status_code == 200, r.text

    latest = client.get("/api/positions").json()
    latest_row = next(p for p in latest if p["asset_id"] == asset["id"])
    assert float(latest_row["flow_in_base"]) == -1100

    growth = _growth_row(client, asset["id"])
    assert growth["growth"] == 100  # realised: the 100 of market growth stays

    total = client.get("/api/positions/growth").json()["total"]
    assert total["growth"] >= 100


# --- 3. crypto asset drops out of held_symbols / /api/prices ---------------

def test_archive_crypto_removes_it_from_held_symbols(client):
    asset = _asset(client, name="Ether", kind="crypto", category="Crypto", units="ETH")
    _position(client, asset["id"], 1, currency="PLN")

    before = client.get("/api/prices").json()
    assert "ETH" in before["crypto"]

    r = client.post(f"/api/assets/{asset['id']}/archive")
    assert r.status_code == 200, r.text

    after = client.get("/api/prices").json()
    assert "ETH" not in after["crypto"]


def test_archive_crypto_symbol_stays_if_another_asset_holds_it(client):
    a1 = _asset(client, name="Ether 1", kind="crypto", category="Crypto", units="ETH")
    a2 = _asset(client, name="Ether 2", kind="crypto", category="Crypto", units="ETH")
    _position(client, a1["id"], 1, currency="PLN")
    _position(client, a2["id"], 2, currency="PLN")

    client.post(f"/api/assets/{a1['id']}/archive")

    after = client.get("/api/prices").json()
    assert "ETH" in after["crypto"]  # a2 still holds it


# --- 4. asset with no snapshots ---------------------------------------------

def test_archive_asset_with_no_snapshots_writes_nothing(client, db):
    asset = _asset(client)

    r = client.post(f"/api/assets/{asset['id']}/archive")
    assert r.status_code == 200, r.text
    assert r.json()["archived_at"] is not None

    assert db.query(func.count(Position.id)).filter(Position.asset_id == asset["id"]).scalar() == 0


# --- 5. archive/unarchive state machine -------------------------------------

def test_archive_twice_is_409(client):
    asset = _asset(client)
    r1 = client.post(f"/api/assets/{asset['id']}/archive")
    assert r1.status_code == 200
    r2 = client.post(f"/api/assets/{asset['id']}/archive")
    assert r2.status_code == 409


def test_unarchive_not_archived_is_409(client):
    asset = _asset(client)
    r = client.post(f"/api/assets/{asset['id']}/unarchive")
    assert r.status_code == 409


def test_unarchive_clears_archived_at(client):
    asset = _asset(client)
    client.post(f"/api/assets/{asset['id']}/archive")

    r = client.post(f"/api/assets/{asset['id']}/unarchive")
    assert r.status_code == 200, r.text
    assert r.json()["archived_at"] is None


# --- 6. ladder data_fresh ignores an archived asset -------------------------

def test_ladder_data_fresh_ignores_archived_stale_asset(client, db):
    asset = _asset(client, name="Stale but archived")
    _position(client, asset["id"], 100)
    pos = db.query(Position).filter(Position.asset_id == asset["id"]).first()
    pos.timestamp = datetime.combine(date.today() - timedelta(days=200), datetime.min.time())
    db.commit()

    client.post(f"/api/assets/{asset['id']}/archive")

    rungs = build_ladder(db)
    rung = next(r for r in rungs if r["key"] == "data_fresh")
    assert asset["name"] not in rung["figures"]["stale_assets"]


# --- 7. history before the archive date is unchanged ------------------------

def test_value_over_time_keeps_history_before_archive(client, db):
    asset = _asset(client)
    pos1 = _position(client, asset["id"], 1000)
    pos = db.query(Position).filter(Position.id == pos1["id"]).first()
    old_day = date.today() - timedelta(days=5)
    pos.timestamp = datetime.combine(old_day, datetime.min.time())
    db.commit()

    client.post(f"/api/assets/{asset['id']}/archive")

    rows = client.get("/api/statistics/value-over-time").json()["rows"]
    by_date = {r["date"]: r["total"] for r in rows}
    day_before_archive = (old_day + timedelta(days=1)).isoformat()
    assert by_date[old_day.isoformat()] == 1000
    assert by_date[day_before_archive] == 1000
    assert by_date[date.today().isoformat()] == 0
