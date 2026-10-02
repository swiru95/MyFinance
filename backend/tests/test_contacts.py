"""Notification e-mail: its own trust domain (src/crypto/contacts.py).

The address comes only from the token's `email` claim, only when the identity
provider says it is verified, and only after the user opts in. It is stored under
the contact key - which opens addresses and nothing else, and which the finances'
keys cannot open. No mail is sent anywhere in this release.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from src import identity
from src.config import settings
from src.crypto import contacts
from src.crypto.core import DecryptionError, KeyRing, aead_open, hkdf
from tests.conftest import account_for, make_client, owner_engine, raw, ring_for

ADDRESS = "alice.private@example.test"


def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _alice(idp, **claims):
    claims.setdefault("email", ADDRESS)
    claims.setdefault("email_verified", True)
    return make_client(idp.token("sub-alice", **claims))


def _uid(sub="sub-alice") -> uuid.UUID:
    return account_for(sub).user_id


def _uidp(uid):
    return uid.hex if owner_engine().dialect.name == "sqlite" else uid


def _contact_row(sub="sub-alice"):
    rows = raw(
        "SELECT email, email_verified, notify_opt_in, unsubscribe_token_hash, token_version "
        "FROM user_contacts WHERE user_id = :u", u=_uidp(_uid(sub)),
    )
    return rows[0] if rows else None


# --- opting in -----------------------------------------------------------------------------------

def test_nobody_is_subscribed_by_default_and_can_opt_in_follows_the_token(idp):
    assert _ok(_alice(idp).get("/api/contacts")) == {"opted_in": False, "can_opt_in": True}
    assert _ok(_alice(idp, email_verified=False).get("/api/contacts"))["can_opt_in"] is False
    assert _ok(make_client(idp.token("sub-nomail")).get("/api/contacts"))["can_opt_in"] is False
    assert _contact_row() is None


def test_opting_in_stores_the_address_encrypted_and_never_returns_it(idp):
    c = _alice(idp)
    r = c.post("/api/contacts/opt-in")
    assert r.status_code == 200 and r.json() == {"opted_in": True, "can_opt_in": True}
    assert ADDRESS not in r.text and "example.test" not in r.text

    email, verified, opted, token_hash, version = _contact_row()
    assert opted in (1, True) and verified in (1, True) and version == 1
    assert ADDRESS.encode() not in bytes(email) and b"example.test" not in bytes(email)
    # Whoever may read addresses (the contact key's holder) can read it back for this user ...
    assert contacts.open_email(_uid(), bytes(email)) == ADDRESS
    # ... only for this user ...
    with pytest.raises(DecryptionError):
        contacts.open_email(uuid.uuid4(), bytes(email))
    # ... and what is stored to recognise the unsubscribe link is its hash, not the token.
    token = contacts.unsubscribe_token(_uid(), 1)
    assert bytes(token_hash) == contacts.token_hash(token) and token.encode() not in bytes(token_hash)
    for table in ("user_contacts", "users"):
        for row in raw(f"SELECT * FROM {table}"):
            for cell in row:
                assert ADDRESS.encode() not in (cell if isinstance(cell, bytes) else str(cell).encode())


def test_without_a_verified_address_in_the_token_there_is_nothing_to_subscribe(idp):
    for claims in ({"email": None}, {"email_verified": False}, {"email_verified": None}, {"email": ""},
                   {"email": "not-an-address"}):
        c = make_client(idp.token("sub-alice", **{"email": ADDRESS, "email_verified": True, **claims}))
        assert c.post("/api/contacts/opt-in").status_code == 409, claims
    assert make_client(idp.token("sub-alice")).post("/api/contacts/opt-in").status_code == 409
    assert _contact_row() is None


def test_a_provider_that_sends_email_verified_as_a_string_is_understood(idp):
    assert _ok(_alice(idp, email_verified="true").post("/api/contacts/opt-in"))["opted_in"] is True


def test_opting_in_needs_a_token_and_the_server_needs_a_contact_key(idp, monkeypatch):
    assert make_client().post("/api/contacts/opt-in").status_code == 401
    monkeypatch.setattr(settings, "contact_key", "")
    c = _alice(idp)
    assert _ok(c.get("/api/contacts"))["can_opt_in"] is False
    assert c.post("/api/contacts/opt-in").status_code == 503


def test_with_authentication_off_there_is_no_token_so_no_address(client):
    assert client.get("/api/contacts").json() == {"opted_in": False, "can_opt_in": False}
    assert client.post("/api/contacts/opt-in").status_code == 409


def test_one_user_never_sees_or_changes_anothers_subscription(idp):
    alice = _alice(idp)
    bob = make_client(idp.token("sub-bob", email="bob@example.test", email_verified=True))
    _ok(alice.post("/api/contacts/opt-in"))
    assert _ok(bob.get("/api/contacts"))["opted_in"] is False
    _ok(bob.post("/api/contacts/opt-out"))
    assert _ok(alice.get("/api/contacts"))["opted_in"] is True


# --- opting out and unsubscribing ------------------------------------------------------------------

def test_opting_out_erases_the_address(idp):
    c = _alice(idp)
    _ok(c.post("/api/contacts/opt-in"))
    assert _ok(c.post("/api/contacts/opt-out")) == {"opted_in": False, "can_opt_in": True}
    email, verified, opted, token_hash, version = _contact_row()
    assert email is None and opted in (0, False)
    assert _ok(c.post("/api/contacts/opt-out"))["opted_in"] is False  # idempotent


def test_the_unsubscribe_link_works_without_signing_in_and_erases_the_address(idp):
    _ok(_alice(idp).post("/api/contacts/opt-in"))
    # What a notifier does: it holds the contact key, so it can build the link's token for any user.
    token = contacts.unsubscribe_token(_uid(), 1)
    anon = make_client()
    r = anon.post("/api/contacts/unsubscribe", json={"token": token})
    assert r.status_code == 200 and r.json() == {"unsubscribed": True}
    email, _, opted, _, _ = _contact_row()
    assert email is None and opted in (0, False)
    assert _ok(_alice(idp).get("/api/contacts"))["opted_in"] is False
    # Clicking it again is harmless.
    assert anon.post("/api/contacts/unsubscribe", json={"token": token}).status_code == 200


def test_a_wrong_or_malformed_token_unsubscribes_nobody(idp):
    _ok(_alice(idp).post("/api/contacts/opt-in"))
    anon = make_client()
    other = contacts.unsubscribe_token(uuid.uuid4(), 1)
    assert anon.post("/api/contacts/unsubscribe", json={"token": other}).status_code == 404
    assert anon.post("/api/contacts/unsubscribe", json={"token": contacts.unsubscribe_token(_uid(), 2)}).status_code == 404
    assert anon.post("/api/contacts/unsubscribe", json={"token": "short"}).status_code == 422
    assert anon.post("/api/contacts/unsubscribe", json={}).status_code == 422
    assert _contact_row()[2] in (1, True)


def test_opting_in_again_issues_a_new_token_so_an_old_link_cannot_cancel_the_new_subscription(idp):
    c = _alice(idp)
    _ok(c.post("/api/contacts/opt-in"))
    old_token = contacts.unsubscribe_token(_uid(), 1)
    _ok(c.post("/api/contacts/opt-out"))
    _ok(c.post("/api/contacts/opt-in"))
    assert _contact_row()[4] == 2
    anon = make_client()
    assert anon.post("/api/contacts/unsubscribe", json={"token": old_token}).status_code == 404
    assert _ok(c.get("/api/contacts"))["opted_in"] is True
    assert anon.post("/api/contacts/unsubscribe", json={"token": contacts.unsubscribe_token(_uid(), 2)}).status_code == 200


def test_opting_in_twice_does_not_rotate_the_token(idp):
    c = _alice(idp)
    _ok(c.post("/api/contacts/opt-in"))
    _ok(c.post("/api/contacts/opt-in"))
    assert _contact_row()[4] == 1


# --- two trust domains ---------------------------------------------------------------------------------

def test_the_contact_key_alone_reads_addresses_but_no_finances(idp):
    """What a notifier would hold - the contact key and the database, no token, no
    KEK - decrypts every address and nothing a user owns."""
    c = _alice(idp)
    asset = _ok(c.post("/api/assets", json={"name": "SecretAsset", "kind": "currency", "category": "Cash", "profile": "safe"}), 201)
    _ok(c.post("/api/positions", json={"asset_id": asset["id"], "amount": 98765.25, "currency": "PLN"}), 201)
    _ok(c.post("/api/contacts/opt-in"))
    uid = _uid()

    # The notifier's reach: every address ...
    rows = raw("SELECT user_id, email FROM user_contacts WHERE email IS NOT NULL")
    assert [contacts.open_email(_uid(), bytes(e)) for _, e in rows] == [ADDRESS]

    # ... and no finance, whichever way it tries to use the key it holds.
    import base64

    key = base64.urlsafe_b64decode(settings.contact_key + "==")
    cells = [
        (table, column, bytes(raw(f"SELECT {column} FROM {table} WHERE user_id = :u LIMIT 1", u=_uidp(uid))[0][0]))
        for table, column in (("assets", "name"), ("positions", "amount"), ("positions", "notes"))
    ]
    for table, column, cell in cells:
        for candidate in (key, hkdf(key, salt=None, info=b"myfinance/v1/contacts/email"),
                          hkdf(key, salt=None, info=("myfinance/v1/table|" + table).encode())):
            for ring_user in (uid, uuid.uuid4()):
                with pytest.raises(DecryptionError):
                    KeyRing(ring_user, candidate).open(table, column, cell)
        with pytest.raises(DecryptionError):
            contacts.open_email(uid, cell)
    # Nor does the key unwrap a data key (it is not a KEK).
    salt, wrapped, version = raw("SELECT key_salt, wrapped_dek, kek_version FROM users WHERE id = :u", u=_uidp(uid))[0]
    from src.crypto.core import unwrap_dek

    for secret in ("sub-alice", ""):
        with pytest.raises((DecryptionError, Exception)):
            unwrap_dek(wrapped, user_id=uid, kek=key, kek_version=version, salt=salt, secret=secret or "x")


def test_the_finance_keys_do_not_open_an_address(idp):
    """And the other way round: the user's key ring and the KEK, which between
    them read every financial value, cannot read the address."""
    _ok(_alice(idp).post("/api/contacts/opt-in"))
    blob = bytes(_contact_row()[0])
    ring = ring_for("sub-alice")
    with pytest.raises(DecryptionError):
        ring.open("user_contacts", "email", blob)
    from src.crypto.core import active_keks

    for kek in active_keks().keys.values():
        with pytest.raises(DecryptionError):
            aead_open(kek, blob, contacts._aad(_uid()))
        with pytest.raises(DecryptionError):
            aead_open(hkdf(kek, salt=None, info=b"myfinance/v1/contacts/email"), blob, contacts._aad(_uid()))
