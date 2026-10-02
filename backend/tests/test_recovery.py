"""The recovery code, end to end through the API: made, shown once, confirmed -
and then used to re-attach an old account's data after the `sub` changed.

The scenario it exists for: the identity provider is replaced (or an account
re-linked), so the same person's next sign-in carries a different `sub`. As far
as the server can tell that is a new person: a new, empty user with a fresh key.
Entering the recovery code there must move the *identity* onto the old data.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from src import identity
from src.config import settings
from src.services import recovery as recovery_service
from tests.conftest import make_client, owner_engine, raw
from tests.fake_oidc import ISSUER

ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}


@pytest.fixture(autouse=True)
def _fresh_limits():
    recovery_service.reset_limits()
    yield
    recovery_service.reset_limits()


def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _as(idp, sub, **claims):
    return make_client(idp.token(sub, **claims))


def _seed(c, tag="Old"):
    _ok(c.put("/api/settings", json={"base_currency": "PLN", "features": ALL_ON}))
    asset = _ok(c.post("/api/assets", json={"name": f"{tag}Asset", "kind": "currency", "category": "Cash", "profile": "safe"}), 201)
    _ok(c.post("/api/positions", json={"asset_id": asset["id"], "amount": 4242.5, "currency": "PLN", "notes": f"{tag}Note"}), 201)
    _ok(c.post("/api/expenses", json={
        "name": f"{tag}Rent", "amount": 1000, "currency": "PLN", "period": "monthly", "category": "x", "starts_on": "2026-01-01",
    }), 201)


def _made_code(c, *, confirm=True) -> str:
    code = _ok(c.post("/api/recovery"), 201)["code"]
    if confirm:
        _ok(c.post("/api/recovery/confirm", json={"code": code}))
    return code


def _user_ids() -> list[str]:
    return [str(r[0]).replace("-", "") for r in raw("SELECT id FROM users WHERE id <> :l", l=_local())]


def _local():
    return identity.LOCAL_USER_ID.hex if owner_engine().dialect.name == "sqlite" else identity.LOCAL_USER_ID


# --- making and confirming the code ----------------------------------------------------------------

def test_a_new_account_has_no_recovery_code(idp):
    c = _as(idp, "sub-old")
    assert _ok(c.get("/api/recovery/status")) == {"locked": False, "configured": False, "confirmed": False, "created_at": None}


def test_the_code_is_shown_once_and_the_server_cannot_show_it_again(idp):
    c = _as(idp, "sub-old")
    r = c.post("/api/recovery")
    assert r.status_code == 201 and r.headers["cache-control"] == "no-store"
    code = r.json()["code"]
    assert code.startswith("MF1-") and len(code.replace("-", "")) == 3 + 50
    status = _ok(c.get("/api/recovery/status"))
    assert status["configured"] is True and status["confirmed"] is False and status["created_at"]
    assert code not in str(status)
    # Nothing the database holds contains the secret half of the code, in any
    # column, as text or bytes. (The id half is the stored lookup handle.)
    secret = code.replace("-", "")[3 + 16 : 3 + 48]
    for table in ("users",):
        for row in raw(f"SELECT * FROM {table}"):
            for cell in row:
                blob = cell if isinstance(cell, bytes) else str(cell).encode()
                assert secret.encode() not in blob and code.encode() not in blob


def test_a_code_counts_only_once_the_user_has_typed_it_back(idp):
    c = _as(idp, "sub-old")
    code = _made_code(c, confirm=False)
    assert _ok(c.get("/api/recovery/status"))["confirmed"] is False
    wrong = code[:-2] + ("22" if not code.endswith("22") else "33")
    assert c.post("/api/recovery/confirm", json={"code": wrong}).status_code == 400
    assert _ok(c.get("/api/recovery/status"))["confirmed"] is False
    assert _ok(c.post("/api/recovery/confirm", json={"code": code.lower()}))["confirmed"] is True
    assert _ok(c.get("/api/recovery/status"))["confirmed"] is True


def test_a_confirmed_code_is_not_replaced_unless_asked_and_the_old_one_then_dies(idp):
    old = _as(idp, "sub-old")
    first = _made_code(old)
    again = old.post("/api/recovery")
    assert again.status_code == 409
    second = _ok(old.post("/api/recovery", json={"replace": True}), 201)["code"]
    assert second != first
    new = _as(idp, "sub-new")
    assert new.post("/api/recovery/restore", json={"code": first}).status_code == 400


def test_the_recovery_endpoints_need_a_token(idp):
    c = make_client()
    for method, path in (("get", "/api/recovery/status"), ("post", "/api/recovery"),
                         ("post", "/api/recovery/confirm"), ("post", "/api/recovery/restore")):
        assert getattr(c, method)(path).status_code == 401, path


# --- the point of it: a changed sub ---------------------------------------------------------------------

def test_the_old_data_is_restored_onto_the_new_identity(idp):
    old = _as(idp, "sub-old")
    _seed(old)
    old_user = _ok(old.get("/api/auth/me"))["user_id"]
    code = _made_code(old)
    assets_before = raw("SELECT count(*) FROM assets")[0][0]

    # The same person after the provider changed: a different sub. A new, empty
    # account - the old data is not theirs as far as anyone can tell.
    new = _as(idp, "sub-new")
    new_user = _ok(new.get("/api/auth/me"))["user_id"]
    assert new_user != old_user
    assert "OldAsset" not in str(_ok(new.get("/api/assets")))
    assert _ok(new.get("/api/recovery/status"))["configured"] is False
    assert raw("SELECT count(*) FROM assets")[0][0] == assets_before + 9  # the new account's default assets

    out = _ok(new.post("/api/recovery/restore", json={"code": code}))
    assert out == {"restored": True, "result": "recovered"}

    # The next request is served as the old user, with the old data, unlocked by
    # the new sub: the identity moved, the data stayed where it was.
    assert _ok(new.get("/api/auth/me"))["user_id"] == old_user
    names = [a["name"] for a in _ok(new.get("/api/assets"))]
    assert "OldAsset" in names
    positions = _ok(new.get("/api/positions"))
    assert any(float(p["amount"]) == 4242.5 and p["notes"] == "OldNote" for p in positions)
    assert any(e["name"] == "OldRent" for e in _ok(new.get("/api/expenses")))

    # Bookkeeping: one user fewer, the old row now answers to the new hash, the
    # empty account's rows are gone, nothing of the old data was copied or lost.
    assert _user_ids() == [old_user.replace("-", "")]
    assert raw("SELECT subject_hash FROM users WHERE id <> :l", l=_local())[0][0] == identity.subject_hash(ISSUER, "sub-new")
    assert raw("SELECT count(*) FROM assets")[0][0] == assets_before  # the new user's nine default assets went
    # The code still works afterwards (it wraps the data key, which did not change).
    assert _ok(new.get("/api/recovery/status"))["confirmed"] is True


def test_after_a_restore_the_old_sub_is_just_another_stranger(idp):
    old = _as(idp, "sub-old")
    _seed(old)
    old_user = _ok(old.get("/api/auth/me"))["user_id"]
    code = _made_code(old)
    new = _as(idp, "sub-new")
    _ok(new.get("/api/assets"))
    _ok(new.post("/api/recovery/restore", json={"code": code}))
    # The old identity no longer finds the data; it becomes a fresh empty account.
    again = _as(idp, "sub-old")
    assert _ok(again.get("/api/auth/me"))["user_id"] != old_user
    assert "OldAsset" not in str(_ok(again.get("/api/assets")))


def test_the_new_identitys_own_data_is_protected_from_being_overwritten(idp):
    old = _as(idp, "sub-old")
    _seed(old)
    code = _made_code(old)
    new = _as(idp, "sub-new")
    asset = _ok(new.post("/api/assets", json={"name": "NewAsset", "kind": "currency", "category": "Cash", "profile": "safe"}), 201)
    _ok(new.post("/api/positions", json={"asset_id": asset["id"], "amount": 5, "currency": "PLN"}), 201)
    users_before = _user_ids()
    r = new.post("/api/recovery/restore", json={"code": code})
    assert r.status_code == 409
    # Nothing moved: both accounts are still there, the new one still has its data.
    assert _user_ids() == users_before and len(users_before) == 2
    assert "NewAsset" in str(_ok(new.get("/api/assets")))


def test_another_users_code_cannot_reach_data_it_does_not_belong_to(idp):
    alice = _as(idp, "sub-alice")
    _seed(alice, "Alice")
    bob = _as(idp, "sub-bob")
    _seed(bob, "Bob")
    bobs_code = _made_code(bob)
    _made_code(alice)
    new = _as(idp, "sub-new")
    _ok(new.get("/api/assets"))
    _ok(new.post("/api/recovery/restore", json={"code": bobs_code}))
    # They got Bob's data - the code is the key to it - and Alice's is untouched.
    assert "BobAsset" in str(_ok(new.get("/api/assets")))
    assert "AliceAsset" not in str(_ok(new.get("/api/assets")))
    assert "AliceAsset" in str(_ok(alice.get("/api/assets")))


# --- wrong codes and the throttle ---------------------------------------------------------------------------

def test_every_kind_of_wrong_code_gets_the_same_answer(idp):
    old = _as(idp, "sub-old")
    code = _made_code(old)
    new = _as(idp, "sub-new")
    other = _as(idp, "sub-other")
    other_code = _made_code(other)
    body = code.replace("-", "")
    flipped = body[:30] + ("Z" if body[30] != "Z" else "Y") + body[31:]
    bad = [
        "", "garbage", code[:-5],                       # malformed
        flipped,                                         # a typo (fails the check characters)
        "MF1-" + "0" * 50,                               # well-formed shape, unknown id
    ]
    answers = set()
    for attempt in bad:
        r = new.post("/api/recovery/restore", json={"code": attempt or " "})
        assert r.status_code in (400, 422), (attempt, r.status_code)
        answers.add(r.text if r.status_code == 400 else "422")
    assert len(answers - {"422"}) == 1, answers
    # Nothing was restored by any of them.
    assert "OldAsset" not in str(_ok(new.get("/api/assets")))


def test_too_many_wrong_codes_lock_the_account_out_even_for_the_right_one(idp, monkeypatch):
    monkeypatch.setattr(settings, "recovery_max_failures", 3)
    monkeypatch.setattr(settings, "recovery_lock_seconds", 900)
    old = _as(idp, "sub-old")
    _seed(old)
    code = _made_code(old)
    new = _as(idp, "sub-new")
    wrong = "MF1-" + "0" * 50
    for _ in range(3):
        assert new.post("/api/recovery/restore", json={"code": wrong}).status_code == 400
    locked = new.post("/api/recovery/restore", json={"code": wrong})
    assert locked.status_code == 429 and 1 <= int(locked.headers["retry-after"]) <= 900
    # The right code is refused too while locked: that is the point of a lock.
    assert new.post("/api/recovery/restore", json={"code": code}).status_code == 429
    assert "OldAsset" not in str(_ok(new.get("/api/assets")))
    # The lock is stored on the account, so it survives a new session and a new
    # replica; lifting it (here: by hand) lets the right code through.
    with owner_engine().begin() as conn:
        conn.execute(text("UPDATE users SET recovery_locked_until = NULL WHERE recovery_failures > 0"))
    assert new.post("/api/recovery/restore", json={"code": code}).status_code == 200


def test_the_lock_grows_with_each_further_failure(idp, monkeypatch):
    monkeypatch.setattr(settings, "recovery_max_failures", 2)
    monkeypatch.setattr(settings, "recovery_lock_seconds", 100)
    new = _as(idp, "sub-new")
    wrong = "MF1-" + "0" * 50
    for _ in range(2):
        new.post("/api/recovery/restore", json={"code": wrong})
    first = raw("SELECT recovery_locked_until FROM users WHERE recovery_failures > 0")[0][0]
    with owner_engine().begin() as conn:
        conn.execute(text("UPDATE users SET recovery_locked_until = NULL WHERE recovery_failures > 0"))
    new.post("/api/recovery/restore", json={"code": wrong})
    second = raw("SELECT recovery_locked_until, recovery_failures FROM users WHERE recovery_failures > 0")[0]
    assert second[1] == 3
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def secs(value):
        value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return (value - now).total_seconds()

    assert 90 <= secs(first) <= 110
    assert 180 <= secs(second[0]) <= 210  # doubled


def test_a_flood_from_many_identities_is_capped_for_the_process(idp, monkeypatch):
    monkeypatch.setattr(recovery_service._global, "limit", 3)
    wrong = "MF1-" + "0" * 50
    codes = []
    for i in range(5):
        c = _as(idp, f"sub-flood-{i}")  # each its own account, so each its own per-user count
        codes.append(c.post("/api/recovery/restore", json={"code": wrong}).status_code)
    assert codes[:3] == [400, 400, 400] and codes[3:] == [429, 429]


def test_a_successful_confirmation_clears_the_failure_count(idp, monkeypatch):
    monkeypatch.setattr(settings, "recovery_max_failures", 5)
    old = _as(idp, "sub-old")
    code = _made_code(old, confirm=False)
    wrong = "MF1-" + "0" * 50
    for _ in range(2):
        assert old.post("/api/recovery/confirm", json={"code": wrong}).status_code == 400
    assert raw("SELECT recovery_failures FROM users WHERE subject_hash = :h", h=identity.subject_hash(ISSUER, "sub-old"))[0][0] == 2
    _ok(old.post("/api/recovery/confirm", json={"code": code}))
    assert raw("SELECT recovery_failures FROM users WHERE subject_hash = :h", h=identity.subject_hash(ISSUER, "sub-old"))[0][0] == 0


# --- the key claim changes but the sub does not ----------------------------------------------------------------------

def test_a_changed_key_claim_locks_the_account_and_the_code_unlocks_it_in_place(idp, monkeypatch):
    """With MYFINANCE_KEY_CLAIM set to a claim other than `sub`, that claim can
    change while `sub` (hence the account) stays. The account then exists but its
    key cannot be unlocked: data endpoints say 423, and the code - used by the
    very same account - wraps the key again for the new claim."""
    monkeypatch.setattr(settings, "key_claim", "uid")
    old = _as(idp, "sub-keep", uid="secret-one")
    _seed(old)
    code = _made_code(old)
    uid = _ok(old.get("/api/auth/me"))["user_id"]

    changed = _as(idp, "sub-keep", uid="secret-two")
    locked = changed.get("/api/assets")
    assert locked.status_code == 423 and "recovery" in locked.text.lower()
    status = _ok(changed.get("/api/recovery/status"))
    assert status["locked"] is True and status["configured"] is True

    out = _ok(changed.post("/api/recovery/restore", json={"code": code}))
    assert out["result"] == "rewrapped"
    assert _ok(changed.get("/api/auth/me"))["user_id"] == uid
    assert "OldAsset" in str(_ok(changed.get("/api/assets")))
    # The old claim value no longer unlocks it; the new one does.
    assert _as(idp, "sub-keep", uid="secret-one").get("/api/assets").status_code == 423


def test_a_token_without_the_key_claim_is_refused(idp, monkeypatch):
    monkeypatch.setattr(settings, "key_claim", "uid")
    r = _as(idp, "sub-x").get("/api/auth/me")
    assert r.status_code == 401 and "uid" in r.text


def test_with_authentication_off_a_code_made_and_restored_keeps_the_local_user_unlocked(client):
    """Local development has no token, so the "claim" is a constant; restoring in
    place must wrap the key for that same constant or the data would lock itself."""
    code = _made_code(client)
    assert client.get("/api/recovery/status").json()["confirmed"] is True
    out = _ok(client.post("/api/recovery/restore", json={"code": code}))
    assert out["result"] == "rewrapped"
    assert client.get("/api/assets").status_code == 200
    assert client.get("/api/recovery/status").json()["locked"] is False
