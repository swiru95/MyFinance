"""Generic OIDC token validation against a fake issuer (see fake_oidc.py), the
Entra-compatible defaults, and creation of the user row on first request.

Every token here is a real RS256 JWT run through the real `verify_token`; only
the two network fetches (discovery document, JWKS) are replaced.
"""
from __future__ import annotations

import json
import logging
import threading

import pytest
from sqlalchemy import select

from src import auth, identity
from src.config import settings
from src.database import engine
from src.models.user import User
from src.scoping import open_system_session
from tests.conftest import make_client
from tests.fake_oidc import AUDIENCE, ISSUER, JWKS_URI, PEPPER, FakeIdP


def _get(token, path="/api/auth/me"):
    return make_client(token).get(path)


def _users() -> list[User]:
    """Signed-in users - the `db` fixture's fixed local user is not one."""
    db = open_system_session()
    try:
        return list(db.execute(select(User).where(User.id != identity.LOCAL_USER_ID)).scalars())
    finally:
        db.close()


# --- accepting and rejecting tokens ---------------------------------------

def test_valid_token_is_accepted_and_returns_only_an_opaque_user_id(idp):
    r = _get(idp.token("sub-alice", name="Alice Example", email="alice@example.test"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authenticated"] is True
    assert set(body) == {"authenticated", "user_id"}
    # It is a UUID, and nothing about the person is in the response.
    import uuid

    uuid.UUID(body["user_id"])
    assert "alice" not in r.text.lower()


def test_no_header_is_401_with_challenge(idp):
    r = make_client().get("/api/assets")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_401(idp):
    assert _get("not-a-jwt").status_code == 401


def test_expired_token_is_401(idp):
    r = _get(idp.token(ttl=-3600))
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_wrong_audience_is_401(idp):
    assert _get(idp.token(aud="some-other-api")).status_code == 401


def test_wrong_issuer_is_401(idp):
    r = _get(idp.token(iss="https://evil.test/realms/lab"))
    assert r.status_code == 401


def test_token_signed_by_an_unpublished_key_is_401(idp):
    assert _get(idp.token(key=FakeIdP.foreign_key())).status_code == 401


def test_unknown_key_id_is_401_not_503(idp):
    assert _get(idp.token(kid="never-published")).status_code == 401


def test_non_string_key_id_is_401_not_a_server_error(idp):
    import base64

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    # PyJWT will not encode such a header, so assemble the token by hand.
    forged = ".".join([b64({"alg": "RS256", "kid": ["a", "b"]}), b64({"sub": "x"}), "c2ln"])
    assert _get(forged).status_code == 401


def test_token_without_a_subject_is_401(idp):
    assert _get(idp.token(drop=("sub",))).status_code == 401


def test_token_without_expiry_is_401(idp):
    assert _get(idp.token(drop=("exp",))).status_code == 401


def test_unreachable_issuer_is_503_not_401(idp):
    idp.down = True
    r = _get(idp.token())
    assert r.status_code == 503


def test_discovery_for_a_different_issuer_is_refused(idp, monkeypatch):
    monkeypatch.setattr(
        idp, "discovery", lambda: {"issuer": "https://other.test", "jwks_uri": JWKS_URI}
    )
    assert _get(idp.token()).status_code == 503


def test_jwks_comes_from_the_discovery_document_and_is_cached(idp):
    token = idp.token()
    assert _get(token).status_code == 200
    assert _get(token).status_code == 200
    # Discovery once, JWKS once - the second request used the cache.
    assert idp.fetched == [
        f"{ISSUER}/.well-known/openid-configuration",
        JWKS_URI,
    ]


def test_key_rotation_is_picked_up_without_a_restart(idp, monkeypatch):
    assert _get(idp.token()).status_code == 200
    idp.rotate("key-2")
    # Within the minimum refresh window the unknown key id is just refused...
    assert _get(idp.token()).status_code == 401
    # ...and once it has passed, the new key set is fetched.
    monkeypatch.setattr(settings, "auth_jwks_min_refresh_seconds", 0)
    assert _get(idp.token()).status_code == 200


def test_hmac_signed_token_is_refused(idp):
    import jwt

    forged = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "exp": 9999999999},
        "secret-secret-secret-secret-secret-secret",
        algorithm="HS256",
        headers={"kid": idp.kid},
    )
    assert _get(forged).status_code == 401


# --- optional Entra checks ----------------------------------------------------

def test_scope_and_role_checks_are_off_for_a_plain_issuer(idp):
    # No scp, no roles: fine, because nothing requires them.
    assert _get(idp.token()).status_code == 200


def test_required_scope_is_enforced_when_configured(idp, monkeypatch):
    monkeypatch.setattr(settings, "auth_api_scope", "finance.read")
    assert _get(idp.token()).status_code == 401
    assert _get(idp.token(scp="openid finance.read")).status_code == 200
    # `scope` (RFC 9068) is accepted as well as Entra's `scp`.
    assert _get(idp.token(scope="finance.read")).status_code == 200


def test_required_role_is_enforced_when_configured(idp, monkeypatch):
    monkeypatch.setattr(settings, "auth_required_role", "finance-user")
    assert _get(idp.token(roles=["other"])).status_code == 403
    assert _get(idp.token(roles=["finance-user"])).status_code == 200


def test_tenant_check_is_enforced_when_configured(idp, monkeypatch):
    monkeypatch.setattr(settings, "auth_tenant_id", "tenant-1")
    assert _get(idp.token(tid="tenant-2")).status_code == 401
    assert _get(idp.token(tid="tenant-1")).status_code == 200


# --- the existing Entra configuration keeps working ------------------------------

ENTRA_TENANT = "11111111-2222-3333-4444-555555555555"
ENTRA_CLIENT = "99999999-8888-7777-6666-000000000000"
ENTRA_V2 = f"https://login.microsoftonline.com/{ENTRA_TENANT}/v2.0"
ENTRA_V1 = f"https://sts.windows.net/{ENTRA_TENANT}/"


@pytest.fixture
def entra(monkeypatch, db):
    """Configured exactly as every existing deployment is: tenant + client id
    (+ pepper), nothing else. The issuer, audiences, `tid`, scope and role
    checks must all follow from that."""
    fake = FakeIdP()
    for name, value in (
        ("auth_issuer", ""),
        ("auth_audience", ""),
        ("auth_tenant_id", ENTRA_TENANT),
        ("auth_client_id", ENTRA_CLIENT),
        ("auth_api_scope", None),
        ("auth_required_role", None),
        ("subject_pepper", PEPPER),
    ):
        monkeypatch.setattr(settings, name, value)

    def fetch(url):
        if url == f"{ENTRA_V2}/.well-known/openid-configuration":
            return {"issuer": ENTRA_V2, "jwks_uri": f"https://login.microsoftonline.com/{ENTRA_TENANT}/discovery/v2.0/keys"}
        if url.endswith("/discovery/v2.0/keys"):
            return fake.jwks()
        raise AssertionError(f"unexpected fetch {url}")

    monkeypatch.setattr(auth, "_fetch_json", fetch)
    auth.reset_key_cache()
    yield fake
    auth.reset_key_cache()


def _entra_token(fake, sub="entra-sub-1", **over):
    claims = dict(
        iss=ENTRA_V2, aud=ENTRA_CLIENT, tid=ENTRA_TENANT,
        scp="access_as_user", roles=["MyFinance.User"],
    )
    claims.update(over)
    return fake.token(sub, **claims)


def test_entra_tenant_and_client_alone_still_enable_auth(entra):
    assert auth.auth_enabled()
    assert auth.issuer() == ENTRA_V2
    assert _get(_entra_token(entra)).status_code == 200


def test_entra_v1_token_is_accepted_and_is_the_same_user_as_v2(entra):
    v2 = _get(_entra_token(entra)).json()["user_id"]
    v1 = _get(_entra_token(entra, iss=ENTRA_V1, aud=f"api://{ENTRA_CLIENT}")).json()["user_id"]
    assert v1 == v2
    assert len(_users()) == 1


def test_entra_defaults_reject_an_id_token_without_scp(entra):
    assert _get(_entra_token(entra, scp=None)).status_code == 401


def test_entra_defaults_require_the_app_role(entra):
    assert _get(_entra_token(entra, roles=[])).status_code == 403


def test_entra_defaults_require_the_tenant(entra):
    assert _get(_entra_token(entra, tid="another-tenant")).status_code == 401


def test_entra_checks_can_still_be_switched_off(entra, monkeypatch):
    monkeypatch.setattr(settings, "auth_api_scope", "")
    monkeypatch.setattr(settings, "auth_required_role", "")
    assert _get(_entra_token(entra, scp=None, roles=[])).status_code == 200


def test_auth_config_for_entra_keeps_its_old_shape_and_adds_the_issuer(entra):
    body = make_client().get("/api/auth/config").json()
    assert body["enabled"] is True
    assert body["tenant_id"] == ENTRA_TENANT
    assert body["client_id"] == ENTRA_CLIENT
    assert body["authority"] == f"https://login.microsoftonline.com/{ENTRA_TENANT}"
    assert body["scopes"] == [f"api://{ENTRA_CLIENT}/access_as_user"]
    assert body["issuer"] == ENTRA_V2


# --- startup configuration check ------------------------------------------

def test_nothing_configured_is_fine():
    auth.validate_config()  # conftest strips the environment


def test_partial_configuration_is_a_startup_error(monkeypatch):
    monkeypatch.setattr(settings, "auth_client_id", "only-a-client-id")
    with pytest.raises(auth.AuthConfigError, match="partly configured"):
        auth.validate_config()


def test_issuer_without_audience_is_a_startup_error(monkeypatch):
    monkeypatch.setattr(settings, "auth_issuer", ISSUER)
    with pytest.raises(auth.AuthConfigError):
        auth.validate_config()


def test_pepper_is_required_when_auth_is_enabled(idp, monkeypatch):
    monkeypatch.setattr(settings, "subject_pepper", "")
    with pytest.raises(auth.AuthConfigError, match="MYFINANCE_SUBJECT_PEPPER"):
        auth.validate_config()


def test_app_refuses_to_start_without_a_pepper(idp, monkeypatch):
    monkeypatch.setattr(settings, "subject_pepper", "")
    from fastapi.testclient import TestClient

    from src.main import app

    with pytest.raises(auth.AuthConfigError):
        with TestClient(app):
            pass


def test_insecure_issuer_is_refused(idp, monkeypatch):
    monkeypatch.setattr(settings, "auth_issuer", "http://idp.example.test")
    with pytest.raises(auth.AuthConfigError, match="https"):
        auth.validate_config()


def test_request_without_a_pepper_fails_closed(idp, monkeypatch):
    monkeypatch.setattr(settings, "subject_pepper", "")
    assert _get(idp.token()).status_code == 500


# --- subject hash ------------------------------------------------------------

def test_subject_hash_is_hmac_sha256_of_iss_pipe_sub():
    import hashlib
    import hmac

    expected = hmac.new(b"pep", b"https://i|abc", hashlib.sha256).hexdigest()
    assert identity.subject_hash("https://i", "abc", pepper="pep") == expected
    assert len(expected) == 64


def test_subject_hash_depends_on_issuer_sub_and_pepper():
    base = identity.subject_hash("https://i", "abc", pepper="p")
    assert identity.subject_hash("https://j", "abc", pepper="p") != base
    assert identity.subject_hash("https://i", "abd", pepper="p") != base
    assert identity.subject_hash("https://i", "abc", pepper="q") != base


def test_subject_hash_needs_a_pepper():
    with pytest.raises(identity.PepperMissing):
        identity.subject_hash("https://i", "abc", pepper="")


# --- user rows --------------------------------------------------------------

def test_user_is_created_on_first_request_and_reused_after(idp):
    assert _users() == []
    token = idp.token("sub-alice")
    first = _get(token).json()["user_id"]
    second = _get(token).json()["user_id"]
    assert first == second
    users = _users()
    assert len(users) == 1
    assert users[0].subject_hash == identity.subject_hash(ISSUER, "sub-alice", pepper=PEPPER)
    assert str(users[0].id) == first
    assert users[0].terms_version is None


def test_different_subjects_are_different_users(idp):
    a = _get(idp.token("sub-alice")).json()["user_id"]
    b = _get(idp.token("sub-bob")).json()["user_id"]
    assert a != b
    assert len(_users()) == 2


def test_new_user_starts_with_the_default_asset_types_and_features_off(idp):
    alice = make_client(idp.token("sub-alice"))
    assets = alice.get("/api/assets").json()
    assert {a["name"] for a in assets} >= {"Cash", "Gold", "Bitcoin", "Savings"}
    assert alice.get("/api/settings").json()["features"] == {
        "portfolio": False, "fire": False, "tax": False, "insights": False,
    }


def test_simultaneous_first_requests_create_exactly_one_user(idp):
    """The SPA fires a page of calls at once on first load."""
    token = idp.token("sub-racer")
    results: list[str] = []
    barrier = threading.Barrier(8)

    def go():
        barrier.wait()
        results.append(_get(token).json()["user_id"])

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 8 and len(set(results)) == 1
    assert len(_users()) == 1


# --- nothing identifying is stored or logged -------------------------------

def test_no_raw_sub_name_or_email_reaches_the_database_or_the_logs(idp, caplog):
    secrets = ["sub-very-identifying-123", "Zelda Fitzgerald", "zelda.f@example.test"]
    caplog.set_level(logging.DEBUG)
    client = make_client(idp.token(secrets[0], name=secrets[1], email=secrets[2],
                                   preferred_username=secrets[2], oid="oid-9f8e7d"))
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/assets", json={"name": "Brokerage", "kind": "currency"}).status_code == 201
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/positions").status_code == 200

    # Every table, every column, as text.
    from sqlalchemy import inspect, text

    with engine.connect() as conn:
        tables = inspect(engine).get_table_names()
        dump = ""
        for t in tables:
            for row in conn.execute(text(f'SELECT * FROM "{t}"')):
                dump += repr(tuple(row)) + "\n"
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    for secret in secrets + ["oid-9f8e7d"]:
        assert secret not in dump, f"{secret!r} was stored"
        assert secret not in log_text, f"{secret!r} was logged"
        assert secret.lower() not in dump.lower()


def test_principal_holds_no_claims():
    p = auth.Principal(identity.LOCAL_USER_ID)
    assert not hasattr(p, "__dict__")
    assert p.user_id == identity.LOCAL_USER_ID


# --- unauthenticated mode ------------------------------------------------------

def test_with_auth_off_everyone_is_the_one_local_user(client):
    assert client.get("/api/auth/me").json() == {
        "authenticated": False,
        "user_id": str(identity.LOCAL_USER_ID),
    }
    assert client.get("/api/auth/config").json() == {"enabled": False}
