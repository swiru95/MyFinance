"""KEK rotation, the key-check value, and what startup refuses.

Rotation is lazy: add a KEK version and each user is wrapped again under it the
next time they sign in (their live token supplies the secret that is needed to
do it). `python -m src.keystatus` says how many are still behind, so the old
version is retired only when none are.
"""
from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from src import auth, identity, keystatus
from src.config import settings
from src.crypto.core import KekError
from src.services import keys as key_service
from tests.conftest import enable_encryption, make_client, owner_engine, raw
from tests.fake_oidc import ISSUER, KEK_V2, KEK_V3

ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}


def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _row(sub):
    return raw(
        "SELECT kek_version, key_salt, wrapped_dek FROM users WHERE subject_hash = :h",
        h=identity.subject_hash(ISSUER, sub),
    )[0]


def _dev_kek() -> str:
    from src.crypto.core import _DEV_KEK

    return base64.urlsafe_b64encode(_DEV_KEK).decode()


def _seeded(idp, sub):
    c = make_client(idp.token(sub))
    asset = _ok(c.post("/api/assets", json={"name": f"{sub}-asset", "kind": "currency", "category": "Cash", "profile": "safe"}), 201)
    _ok(c.post("/api/positions", json={"asset_id": asset["id"], "amount": 777.25, "currency": "PLN"}), 201)
    return c


def _names(c):
    return [a["name"] for a in _ok(c.get("/api/assets"))]


def _report() -> dict:
    with owner_engine().connect() as conn:
        return key_service.version_report(conn)


# --- lazy rewrap ----------------------------------------------------------------------------------

def test_a_new_kek_version_rewraps_each_user_on_their_next_sign_in(idp, monkeypatch):
    alice, bob = _seeded(idp, "sub-alice"), _seeded(idp, "sub-bob")
    assert _row("sub-alice")[0] == _row("sub-bob")[0] == 2

    # Operations: add version 3 to the Secret (version 2 stays until nobody is on it).
    enable_encryption(monkeypatch, keks=f"3:{KEK_V3},2:{KEK_V2},1:{_dev_kek()}")
    before = _report()
    assert before["current"] == 3 and before["by_version"] == {1: 1, 2: 2}  # the local user, alice, bob
    assert before["behind"] == 3

    alice_before = _row("sub-alice")
    assert "sub-alice-asset" in _names(alice)  # served normally on her old version, and rewrapped by it
    after = _row("sub-alice")
    assert after[0] == 3
    assert after[1] != alice_before[1] and after[2] != alice_before[2]  # fresh salt, new wrapping
    assert _row("sub-bob")[0] == 2  # not signed in yet: untouched

    report = _report()
    assert report["by_version"] == {1: 1, 2: 1, 3: 1} and report["behind"] == 2

    # The data is exactly as it was; only its key's wrapping moved.
    positions = _ok(alice.get("/api/positions"))
    assert [float(p["amount"]) for p in positions] == [777.25]

    assert "sub-bob-asset" in _names(bob)
    assert _row("sub-bob")[0] == 3
    assert _report()["by_version"] == {1: 1, 3: 2}


def test_the_rewrapped_key_opens_under_the_new_kek_alone(idp, monkeypatch):
    alice = _seeded(idp, "sub-alice")
    enable_encryption(monkeypatch, keks=f"3:{KEK_V3},2:{KEK_V2},1:{_dev_kek()}")
    _names(alice)  # rewrap
    # Version 2 is no longer needed for her: drop it and she still gets in.
    monkeypatch.setattr(settings, "keks", f"3:{KEK_V3},1:{_dev_kek()}")
    assert "sub-alice-asset" in _names(alice)


def test_a_user_still_on_a_removed_version_is_refused_not_silently_given_a_new_key(idp, monkeypatch):
    carol = _seeded(idp, "sub-carol")
    # v2 dropped from the Secret too early. (Set directly: the schema job, which
    # enable_encryption stands in for, would have refused - see the next test.)
    monkeypatch.setattr(settings, "keks", f"3:{KEK_V3},1:{_dev_kek()}")
    r = carol.get("/api/assets")
    assert r.status_code == 503 and "encryption configuration" in r.text
    # She was not given a fresh key (which would orphan her data): her row is unchanged.
    assert _row("sub-carol")[0] == 2


def test_the_schema_job_will_not_drop_a_version_users_are_still_on(idp, monkeypatch):
    _seeded(idp, "sub-carol")
    monkeypatch.setattr(settings, "keks", f"3:{KEK_V3},1:{_dev_kek()}")
    with owner_engine().begin() as conn:
        with pytest.raises(KekError, match=r"v2 \(1 user\)"):
            key_service.ensure_key_check(conn)


def test_keystatus_reports_how_many_are_behind(idp, monkeypatch, capsys):
    alice = _seeded(idp, "sub-alice")
    enable_encryption(monkeypatch, keks=f"3:{KEK_V3},2:{KEK_V2},1:{_dev_kek()}")
    # It must run as the owner (as the schema job does): as the runtime role,
    # row-level security hides the other users and it refuses to report.
    monkeypatch.setattr(keystatus, "engine", owner_engine())
    assert keystatus.main([]) == 0
    out = capsys.readouterr().out
    assert "current KEK version: 3" in out and "KEK v2: 1 user(s)  [BEHIND]" in out
    assert "behind the current version: 2" in out  # alice, and the local development user (v1)
    assert keystatus.main(["--fail-on-behind"]) == 1
    capsys.readouterr()

    _names(alice)  # alice signs in: rewrapped to 3
    # Take the development user out of the picture (it is only the test harness's).
    local = identity.LOCAL_USER_ID.hex if owner_engine().dialect.name == "sqlite" else identity.LOCAL_USER_ID
    with owner_engine().begin() as conn:
        conn.execute(text("DELETE FROM settings WHERE user_id = :l"), {"l": local})
        conn.execute(text("DELETE FROM users WHERE id = :l"), {"l": local})
    assert keystatus.main(["--fail-on-behind"]) == 0
    out = capsys.readouterr().out
    assert "behind the current version: 0" in out and "older KEKs can be retired" in out


def test_a_keyless_user_is_reported_apart_and_gets_a_key_at_first_sign_in(idp):
    """A user who existed before encryption and has no data: no key until they
    sign in (the schema job refuses to leave rows of anyone else in plaintext)."""
    sub = "sub-old-timer"
    with owner_engine().begin() as conn:
        import uuid

        uid = uuid.uuid4()
        conn.execute(
            text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, :t)"),
            {"i": uid if owner_engine().dialect.name == "postgresql" else uid.hex,
             "h": identity.subject_hash(ISSUER, sub), "t": "2026-01-01 00:00:00"},
        )
    assert _report()["keyless"] == 1
    c = make_client(idp.token(sub))
    assert _ok(c.get("/api/assets")) == []  # no default assets for an existing user, but it works
    assert _report()["keyless"] == 0 and _row(sub)[0] == 2


# --- the key-check value -----------------------------------------------------------------------------

def test_a_wrong_kek_is_caught_at_startup_before_anything_is_written(idp, monkeypatch):
    # The database was initialised under KEK_V2 (idp fixture). A Secret that holds
    # another key under the same version number is a typo, an old value or another
    # environment's - and must stop the process, not quietly create users under it.
    wrong = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(settings, "keks", f"2:{wrong}")
    from src.main import app

    users_before = raw("SELECT count(*) FROM users")[0][0]
    with pytest.raises(KekError, match="version 2 does not open the key-check value"):
        with TestClient(app):
            pass
    assert raw("SELECT count(*) FROM users")[0][0] == users_before


def test_startup_wants_the_current_versions_check_value_to_exist(idp, monkeypatch):
    from src.main import app

    # v9 is new: the schema job has not seen it.
    monkeypatch.setattr(settings, "keks", f"9:{KEK_V3},2:{KEK_V2},1:{_dev_kek()}")
    with pytest.raises(KekError, match="no key-check value for the current KEK version 9"):
        with TestClient(app):
            pass
    with owner_engine().begin() as conn:  # ... the schema job runs ...
        key_service.ensure_key_check(conn)
    with TestClient(app):
        pass


def test_the_check_value_table_is_missing_before_the_schema_job_ran(idp, monkeypatch):
    from src.main import app

    with owner_engine().begin() as conn:
        conn.execute(text("DROP TABLE key_check"))
    with pytest.raises(KekError, match="schema job"):
        with TestClient(app):
            pass


# --- startup refusals with authentication on -------------------------------------------------------------------

def test_authentication_on_requires_a_kek(idp, monkeypatch):
    monkeypatch.setattr(settings, "keks", "")
    with pytest.raises(auth.AuthConfigError, match="MYFINANCE_KEKS"):
        auth.validate_config()
    from src.main import app

    with pytest.raises(auth.AuthConfigError):
        with TestClient(app):
            pass


@pytest.mark.parametrize("bad", ["nonsense", "1:short", "x:" + "A" * 43])
def test_a_malformed_kek_is_refused_at_startup(idp, monkeypatch, bad):
    monkeypatch.setattr(settings, "keks", bad)
    with pytest.raises(auth.AuthConfigError):
        auth.validate_config()


def test_authentication_on_requires_the_contact_key(idp, monkeypatch):
    monkeypatch.setattr(settings, "contact_key", "")
    with pytest.raises(auth.AuthConfigError, match="CONTACT_KEY"):
        auth.validate_config()
    from src.main import app

    with pytest.raises(auth.AuthConfigError):
        with TestClient(app):
            pass


def test_a_short_contact_key_is_refused(idp, monkeypatch):
    monkeypatch.setattr(settings, "contact_key", base64.urlsafe_b64encode(b"too short").decode())
    with pytest.raises(auth.AuthConfigError, match="at least 32"):
        auth.validate_config()


def test_the_key_claim_must_be_named(idp, monkeypatch):
    monkeypatch.setattr(settings, "key_claim", "")
    with pytest.raises(auth.AuthConfigError, match="KEY_CLAIM"):
        auth.validate_config()


def test_with_authentication_off_the_public_development_kek_is_used_and_flagged(db, client):
    from src.crypto.core import active_keks

    keks = active_keks()
    assert keks.development and keks.current == 1
    # ... and the data is still stored encrypted by the same code.
    assert raw("SELECT value FROM settings LIMIT 1")[0][0][:1] == b"\x01"
