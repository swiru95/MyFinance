"""Settings: the feature-flag defaults schema.py seeds, the GET/PUT round
trip, and the fire -> portfolio dependency enforced server-side.
"""
import json
from datetime import date

from src import schema
from src.models.income import IncomeSource
from src.models.report import Report
from src.models.settings import Setting

ALL_OFF = {"portfolio": False, "fire": False, "tax": False, "insights": False}
ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}


def _clear_features(db):
    # The `db` fixture pre-seeds "features" all-on for the rest of the suite
    # (see conftest.py) - these tests are about the seeding step itself, so
    # they start from the same "key absent" state a brand-new database has.
    db.query(Setting).filter(Setting.key == "features").delete()
    db.commit()


# --- schema.seed_features(): defaults ---------------------------------------

def test_seed_features_all_false_on_empty_db(db):
    _clear_features(db)
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    assert row is not None
    assert json.loads(row.value) == ALL_OFF


def test_seed_features_all_true_when_positions_exist(client, db):
    _clear_features(db)
    r = client.post(
        "/api/assets",
        json={"name": "Cash", "kind": "currency", "category": "Cash", "profile": "safe"},
    )
    asset_id = r.json()["id"]
    client.post(
        "/api/positions",
        json={"asset_id": asset_id, "amount": 100, "currency": "PLN"},
    )
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    assert json.loads(row.value) == ALL_ON


def test_seed_features_all_true_when_income_source_exists(db):
    _clear_features(db)
    db.add(IncomeSource(
        name="Job", kind="uop", currency="PLN", params={}, starts_on=date(2024, 1, 1),
    ))
    db.commit()
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    assert json.loads(row.value) == ALL_ON


def test_seed_features_all_true_when_fire_settings_exist(db):
    _clear_features(db)
    db.add(Setting(key="fire", value="{}"))
    db.commit()
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    assert json.loads(row.value) == ALL_ON


def test_seed_features_all_true_when_report_exists(db):
    _clear_features(db)
    db.add(Report(status="done", style="balanced", language="en"))
    db.commit()
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    assert json.loads(row.value) == ALL_ON


def test_seed_features_never_overwrites_a_later_choice(db):
    _clear_features(db)
    schema.seed_features()
    row = db.query(Setting).filter(Setting.key == "features").first()
    row.value = json.dumps({"portfolio": True, "fire": False, "tax": False, "insights": False})
    db.commit()

    schema.seed_features()  # a second schema run (e.g. next release)

    row = db.query(Setting).filter(Setting.key == "features").first()
    assert json.loads(row.value)["portfolio"] is True


# --- GET/PUT round trip ------------------------------------------------------

def test_get_settings_always_returns_features(client):
    body = client.get("/api/settings").json()
    assert set(body["features"]) == {"portfolio", "fire", "tax", "insights"}


def test_put_settings_round_trips_features(client):
    r = client.put(
        "/api/settings",
        json={"base_currency": "PLN", "features": {
            "portfolio": True, "fire": False, "tax": True, "insights": False,
        }},
    )
    assert r.status_code == 200, r.text
    assert r.json()["features"] == {
        "portfolio": True, "fire": False, "tax": True, "insights": False,
    }
    # And it stuck.
    assert client.get("/api/settings").json()["features"] == {
        "portfolio": True, "fire": False, "tax": True, "insights": False,
    }


def test_put_settings_without_features_leaves_them_untouched(client):
    client.put(
        "/api/settings",
        json={"base_currency": "PLN", "features": {
            "portfolio": True, "fire": True, "tax": False, "insights": False,
        }},
    )
    r = client.put("/api/settings", json={"base_currency": "EUR"})
    assert r.status_code == 200, r.text
    assert r.json()["features"] == {
        "portfolio": True, "fire": True, "tax": False, "insights": False,
    }


# --- fire -> portfolio dependency --------------------------------------------

def test_put_settings_enabling_fire_without_portfolio_is_rejected_to_off(client):
    """The API does not silently flip portfolio on to satisfy a fire=true it
    was not asked to grant - it corrects the inconsistent request by turning
    fire back off, since fire cannot stand without portfolio."""
    r = client.put(
        "/api/settings",
        json={"base_currency": "PLN", "features": {
            "portfolio": False, "fire": True, "tax": False, "insights": False,
        }},
    )
    assert r.status_code == 200, r.text
    assert r.json()["features"]["fire"] is False
    assert r.json()["features"]["portfolio"] is False


# --- terms of use acceptance -------------------------------------------------

def test_get_settings_exposes_terms_state_before_acceptance(client):
    body = client.get("/api/settings").json()
    assert body["terms"] == {
        "current_version": 1,
        "accepted_version": None,
        "accepted_at": None,
    }


def test_post_terms_accept_with_current_version_records_it(client):
    r = client.post("/api/settings/terms/accept", json={"version": 1})
    assert r.status_code == 200, r.text
    terms = r.json()["terms"]
    assert terms["accepted_version"] == 1
    assert terms["accepted_at"] is not None
    # And it stuck.
    assert client.get("/api/settings").json()["terms"] == terms


def test_post_terms_accept_with_wrong_version_is_rejected(client):
    r = client.post("/api/settings/terms/accept", json={"version": 2})
    assert r.status_code == 422, r.text
    # Nothing recorded.
    assert client.get("/api/settings").json()["terms"]["accepted_version"] is None


def test_put_settings_disabling_portfolio_disables_fire(client):
    client.put(
        "/api/settings",
        json={"base_currency": "PLN", "features": {
            "portfolio": True, "fire": True, "tax": False, "insights": False,
        }},
    )
    r = client.put(
        "/api/settings",
        json={"base_currency": "PLN", "features": {
            "portfolio": False, "fire": True, "tax": False, "insights": False,
        }},
    )
    assert r.status_code == 200, r.text
    assert r.json()["features"] == ALL_OFF
