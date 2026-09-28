"""DELETE /api/assets/{asset_id}: delete asset and all its position snapshots."""


def test_delete_asset_returns_204(client):
    """DELETE /api/assets/{asset_id} returns 204 No Content."""
    asset = client.post(
        "/api/assets", json={"name": "Test asset", "kind": "currency"}
    ).json()

    r = client.delete(f"/api/assets/{asset['id']}")
    assert r.status_code == 204


def test_delete_asset_removes_it_from_list(client):
    """Asset is gone from GET /api/assets after deletion."""
    asset = client.post(
        "/api/assets", json={"name": "Test asset", "kind": "currency"}
    ).json()
    asset_id = asset["id"]

    # Verify it's there before deletion
    assets_before = client.get("/api/assets").json()
    assert any(a["id"] == asset_id for a in assets_before)

    # Delete it
    client.delete(f"/api/assets/{asset_id}")

    # Verify it's gone
    assets_after = client.get("/api/assets").json()
    assert not any(a["id"] == asset_id for a in assets_after)


def test_delete_asset_removes_all_its_positions(client):
    """All position snapshots for the deleted asset are removed.

    GET /api/positions returns only the latest snapshot per asset, but the
    database should still have all snapshots removed on asset deletion.
    """
    asset = client.post(
        "/api/assets", json={"name": "Test asset", "kind": "currency"}
    ).json()
    asset_id = asset["id"]

    # Create two position snapshots (second one replaces first as "latest" in GET response)
    pos1 = client.post(
        "/api/positions",
        json={"asset_id": asset_id, "amount": 100, "currency": "PLN"},
    ).json()
    pos2 = client.post(
        "/api/positions",
        json={"asset_id": asset_id, "amount": 200, "currency": "PLN"},
    ).json()

    pos_ids = {pos1["id"], pos2["id"]}

    # Verify the latest position is there before deletion
    positions_before = client.get("/api/positions").json()
    found = [p for p in positions_before if p["id"] in pos_ids]
    assert len(found) == 1  # Only the latest snapshot appears in GET response
    assert found[0]["id"] == pos2["id"]

    # Delete the asset
    client.delete(f"/api/assets/{asset_id}")

    # Verify all positions are gone (both snapshots)
    positions_after = client.get("/api/positions").json()
    found_after = [p for p in positions_after if p["id"] in pos_ids]
    assert len(found_after) == 0


def test_delete_asset_removes_from_growth(client):
    """Asset is removed from GET /api/positions/growth after deletion."""
    asset = client.post(
        "/api/assets", json={"name": "Test asset", "kind": "currency"}
    ).json()
    asset_id = asset["id"]

    # Create two positions and update one to get a growth snapshot
    pos1 = client.post(
        "/api/positions",
        json={"asset_id": asset_id, "amount": 100, "currency": "PLN"},
    ).json()
    pos2 = client.post(
        "/api/positions",
        json={"asset_id": asset_id, "amount": 200, "currency": "PLN"},
    ).json()

    # Update pos1 to create a growth snapshot
    client.put(
        f"/api/positions/{pos1['id']}",
        json={"amount": 120, "currency": "PLN", "flow": 10},
    )

    # Verify the asset appears in growth
    growth_before = client.get("/api/positions/growth").json()
    assert any(a["asset_id"] == asset_id for a in growth_before["assets"])

    # Delete the asset
    client.delete(f"/api/assets/{asset_id}")

    # Verify the asset is gone from growth
    growth_after = client.get("/api/positions/growth").json()
    assert not any(a["asset_id"] == asset_id for a in growth_after["assets"])


def test_delete_nonexistent_asset_is_404(client):
    """DELETE on a nonexistent asset returns 404."""
    r = client.delete("/api/assets/999999")
    assert r.status_code == 404
