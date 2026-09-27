"""Asset wrapper tagging (IKE/IKZE/PPK/OIPE/OKI) and the new PUT /api/assets/{id}."""
import pytest


def test_create_with_wrapper(client):
    r = client.post(
        "/api/assets",
        json={"name": "IKE broker", "kind": "currency", "category": "Retirement", "wrapper": "ike"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["wrapper"] == "ike"


def test_put_changes_wrapper(client):
    created = client.post("/api/assets", json={"name": "PPK", "kind": "currency"})
    asset_id = created.json()["id"]
    assert created.json()["wrapper"] == ""

    updated = client.put(f"/api/assets/{asset_id}", json={"wrapper": "ppk"})
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["wrapper"] == "ppk"
    # Untouched fields survive a partial update.
    assert body["name"] == "PPK"


def test_put_partial_update_only_touches_given_fields(client):
    created = client.post(
        "/api/assets",
        json={"name": "Old name", "kind": "currency", "category": "Cash", "icon": "X"},
    )
    asset_id = created.json()["id"]

    updated = client.put(f"/api/assets/{asset_id}", json={"name": "New name"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "New name"
    assert body["category"] == "Cash"
    assert body["icon"] == "X"


def test_put_missing_asset_is_404(client):
    r = client.put("/api/assets/999999", json={"name": "Nope"})
    assert r.status_code == 404


def test_invalid_wrapper_on_create_is_422(client):
    r = client.post(
        "/api/assets", json={"name": "Bad", "kind": "currency", "wrapper": "roth-ira"}
    )
    assert r.status_code == 422


def test_invalid_wrapper_on_update_is_422(client):
    created = client.post("/api/assets", json={"name": "Ok asset", "kind": "currency"})
    asset_id = created.json()["id"]
    r = client.put(f"/api/assets/{asset_id}", json={"wrapper": "roth-ira"})
    assert r.status_code == 422


def test_allocation_items_carry_wrapper(client):
    asset = client.post(
        "/api/assets",
        json={"name": "IKZE fund", "kind": "currency", "category": "Retirement", "wrapper": "ikze"},
    ).json()
    client.post("/api/positions", json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"})

    alloc = client.get("/api/statistics/allocation").json()
    items = [i for i in alloc["items"] if i["asset_id"] == asset["id"]]
    assert len(items) == 1
    assert items[0]["wrapper"] == "ikze"


def test_allocation_items_default_to_empty_wrapper(client):
    asset = client.post("/api/assets", json={"name": "Plain cash", "kind": "currency"}).json()
    client.post("/api/positions", json={"asset_id": asset["id"], "amount": 500, "currency": "PLN"})

    alloc = client.get("/api/statistics/allocation").json()
    items = [i for i in alloc["items"] if i["asset_id"] == asset["id"]]
    assert items[0]["wrapper"] == ""


def test_create_with_oki_wrapper(client):
    r = client.post(
        "/api/assets",
        json={"name": "OKI broker", "kind": "currency", "category": "Stocks", "wrapper": "oki"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["wrapper"] == "oki"


def test_allocation_by_wrapper_ordered_and_totalled(client):
    cash = client.post("/api/assets", json={"name": "Cash", "kind": "currency"}).json()
    client.post("/api/positions", json={"asset_id": cash["id"], "amount": 100_000, "currency": "PLN"})

    ike = client.post(
        "/api/assets", json={"name": "IKE", "kind": "currency", "wrapper": "ike"}
    ).json()
    client.post("/api/positions", json={"asset_id": ike["id"], "amount": 20_000, "currency": "PLN"})

    oki = client.post(
        "/api/assets", json={"name": "OKI", "kind": "currency", "wrapper": "oki"}
    ).json()
    client.post("/api/positions", json={"asset_id": oki["id"], "amount": 40_000, "currency": "PLN"})

    alloc = client.get("/api/statistics/allocation").json()
    by_wrapper = alloc["by_wrapper"]

    # ike listed before oki regardless of insertion order (ike, ikze, ppk, oipe, oki).
    assert [w["wrapper"] for w in by_wrapper] == ["ike", "oki"]
    ike_row = next(w for w in by_wrapper if w["wrapper"] == "ike")
    oki_row = next(w for w in by_wrapper if w["wrapper"] == "oki")
    assert ike_row["value"] == pytest.approx(20_000)
    assert ike_row["assets"] == 1
    assert oki_row["value"] == pytest.approx(40_000)

    total = alloc["total"]
    assert alloc["tax_advantaged_total"] == pytest.approx(60_000)
    assert alloc["tax_advantaged_percent"] == pytest.approx(100.0 * 60_000 / total)


def test_allocation_by_wrapper_empty_when_nothing_wrapped(client):
    asset = client.post("/api/assets", json={"name": "Plain", "kind": "currency"}).json()
    client.post("/api/positions", json={"asset_id": asset["id"], "amount": 1000, "currency": "PLN"})

    alloc = client.get("/api/statistics/allocation").json()
    assert alloc["by_wrapper"] == []
    assert alloc["tax_advantaged_total"] == 0.0
    assert alloc["tax_advantaged_percent"] == 0.0
