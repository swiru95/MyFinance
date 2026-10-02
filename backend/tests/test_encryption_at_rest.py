"""What the database holds, and what it takes to read it.

Seeds a user's wallet through the API, then looks at the database the way someone
with a dump would - raw SQL, no key - and then tries to read it the ways an
attacker or a bug could: with the KEK but another `sub`, with the `sub` but another
KEK, with a ciphertext moved to another user or column.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from src import identity
from src.config import settings
from src.crypto.core import (
    DecryptionError,
    KeyExpired,
    KeyRing,
    KeysUnavailable,
    activated,
    active_keks,
    unwrap_dek,
)
from src.database import KEYRING_KEY, SessionLocal, engine
from src.models import Asset, Expense, Position, Report, Setting
from src.scoping import open_session
from tests.conftest import account_for, make_client, owner_engine, raw, ring_for, system_session
from tests.fake_oidc import ISSUER

ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}

# Distinctive values: seeded through the API, they must not be findable anywhere.
NAMES = ["ZlotyHoardAsset", "ZlotyHoardCat", "ZlotyRent", "ZlotyHousing", "ZlotyJob", "ZlotyNote", "ZlotyPositionNote"]
AMOUNT = 123456.5
EXPENSE_AMOUNT = 4321.09
NUMBER_TEXTS = ["123456.5", "123456.50", "4321.09", "98765.43"]


def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _seed(c) -> dict:
    _ok(c.put("/api/settings", json={"base_currency": "PLN", "features": ALL_ON}))
    ids = {}
    asset = _ok(c.post("/api/assets", json={
        "name": "ZlotyHoardAsset", "kind": "currency", "category": "ZlotyHoardCat", "profile": "safe",
    }), 201)
    ids["asset"] = asset["id"]
    ids["position"] = _ok(c.post("/api/positions", json={
        "asset_id": asset["id"], "amount": AMOUNT, "currency": "PLN", "notes": "ZlotyPositionNote",
    }), 201)["id"]
    ids["expense"] = _ok(c.post("/api/expenses", json={
        "name": "ZlotyRent", "amount": EXPENSE_AMOUNT, "currency": "PLN", "period": "monthly",
        "category": "ZlotyHousing", "starts_on": "2026-01-01", "notes": "ZlotyNote",
    }), 201)["id"]
    src = _ok(c.post("/api/income/sources", json={
        "name": "ZlotyJob", "kind": "uop", "currency": "PLN",
        "params": {"gross_monthly": 98765.43, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2026-01-01",
    }), 201)
    ids["source"] = src["id"]
    _ok(c.put(f"/api/income/sources/{src['id']}/entries/2026-03", json={"amount": 98765.43, "notes": "ZlotyNote"}))
    _ok(c.put("/api/monthly/2026-03", json={"income": 98765.43, "actual_spent": 4321.09, "currency": "PLN", "notes": "ZlotyNote"}))
    _ok(c.put("/api/settings/birth-year", json={"birth_year": 1987}))
    return ids


@pytest.fixture
def alice(idp):
    c = make_client(idp.token("sub-alice"))
    _seed(c)
    return c


# --- raw SQL shows no plaintext -------------------------------------------------------------------

def _every_cell() -> list[tuple[str, str, object]]:
    """(table, column, value) for everything in every table, as stored."""
    out = []
    with owner_engine().connect() as conn:
        tables = [r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            if owner_engine().dialect.name == "postgresql"
            else "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ))]
        for table in tables:
            result = conn.execute(text(f'SELECT * FROM "{table}"'))
            cols = list(result.keys())
            for row in result:
                for col, value in zip(cols, row):
                    out.append((table, col, value))
    return out


def _as_bytes(value) -> bytes:
    if value is None:
        return b""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return str(value).encode("utf-8")


def test_no_seeded_name_note_or_amount_appears_in_any_cell(alice):
    cells = _every_cell()
    assert len(cells) > 150
    for table, column, value in cells:
        blob = _as_bytes(value)
        for needle in NAMES + NUMBER_TEXTS:
            assert needle.encode() not in blob, f"{table}.{column} holds {needle!r} in the clear"
        # Numbers that are still numbers: none of the seeded figures may be one.
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            for figure in (AMOUNT, EXPENSE_AMOUNT, 98765.43, 1987):
                assert abs(float(value) - figure) > 1e-9, f"{table}.{column} holds the figure {figure}"


def test_no_seeded_value_is_in_the_database_file_either(alice):
    """Not only the rows: the bytes on disk, pages, journal and free space included
    (SQLite; on PostgreSQL the equivalent is the SQL-level check above)."""
    if engine.dialect.name != "sqlite":
        pytest.skip("reads the SQLite file")
    path = Path(engine.url.database)
    data = b"".join(p.read_bytes() for p in path.parent.glob(path.name + "*"))
    assert b"CREATE TABLE" in data
    for needle in NAMES + NUMBER_TEXTS:
        assert needle.encode() not in data, needle


def test_the_database_holds_ciphertext_where_the_api_shows_values(alice):
    with owner_engine().connect() as conn:
        name_blob = conn.execute(text("SELECT name FROM assets WHERE name IS NOT NULL ORDER BY id DESC LIMIT 1")).scalar()
        amount_blob = conn.execute(text("SELECT amount FROM positions LIMIT 1")).scalar()
    for blob in (name_blob, amount_blob):
        blob = bytes(blob)
        assert blob[:1] == b"\x01" and len(blob) >= 1 + 12 + 16
    assert alice.get("/api/assets").json()[-1]["name"] == "ZlotyHoardAsset"
    assert float(alice.get("/api/positions").json()[0]["amount"]) == AMOUNT


def test_only_the_documented_columns_are_in_the_clear(alice):
    """The column inventory in the README, enforced: every column that is not an
    encrypted type is on this list, with the reason it may stay plaintext."""
    from src.database import Base

    allowed_plain = {
        # ids and keys
        "id", "user_id", "asset_id", "source_id", "key", "subject_hash", "kek_version", "token_version",
        "recovery_id", "recovery_failures",
        # job state and timestamps
        "status", "status_note", "created_at", "updated_at", "timestamp", "archived_at",
        "terms_version", "terms_accepted_at", "recovery_created_at", "recovery_confirmed_at",
        "recovery_locked_until",
        # enumerations/labels the app filters or sorts by, and months that sit in unique constraints
        "kind", "period", "language", "month", "model", "translator",
        # key material and ciphertext handled outside the column types
        "key_salt", "wrapped_dek", "recovery_salt", "recovery_kdf", "recovery_wrapped_dek",
        "recovery_verifier", "email", "email_verified", "notify_opt_in", "unsubscribe_token_hash",
        "check_value",
    }
    from src.crypto.fields import Encrypted

    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if isinstance(col.type, Encrypted):
                continue
            assert col.name in allowed_plain, f"{table.name}.{col.name} is plaintext but not on the documented list"


# --- decryption fails ----------------------------------------------------------------------------------

def _alice_user_id() -> uuid.UUID:
    return account_for("sub-alice").user_id


def _blob(sql: str, **params):
    return bytes(raw(sql, **params)[0][0])


def _uid(user_id: uuid.UUID):
    """A user id as this database stores it (SQLite keeps it as 32 hex digits)."""
    return user_id.hex if owner_engine().dialect.name == "sqlite" else user_id


def test_the_kek_and_the_database_without_the_users_sub_decrypt_nothing(alice):
    uid = _alice_user_id()
    salt, wrapped, version = raw(
        "SELECT key_salt, wrapped_dek, kek_version FROM users WHERE subject_hash = :h",
        h=identity.subject_hash(ISSUER, "sub-alice"),
    )[0]
    keks = active_keks()
    # Right KEK, right salt, right ciphertext - and every sub but hers.
    for wrong in ("sub-bob", "alice", "sub-alice2", "SUB-ALICE", "sub-alice "):
        with pytest.raises(DecryptionError):
            unwrap_dek(wrapped, user_id=uid, kek=keks.get(version), kek_version=version, salt=salt, secret=wrong)
    # Through the front door: the same user with another sub is a locked account, no key.
    account = account_for("sub-alice")
    assert account.keyring is not None  # sanity: hers does open it
    from src.services.users import login

    locked = login(identity.subject_hash(ISSUER, "sub-alice"), "not-her-sub")
    assert locked.locked and locked.keyring is None


def test_the_sub_without_the_kek_decrypts_nothing(alice, monkeypatch):
    uid = _alice_user_id()
    salt, wrapped, version = raw(
        "SELECT key_salt, wrapped_dek, kek_version FROM users WHERE subject_hash = :h",
        h=identity.subject_hash(ISSUER, "sub-alice"),
    )[0]
    other_kek = bytes(32)
    with pytest.raises(DecryptionError):
        unwrap_dek(wrapped, user_id=uid, kek=other_kek, kek_version=version, salt=salt, secret="sub-alice")
    # And a deployment whose Secret holds a different key under the same version
    # unlocks nothing: signing in as her yields a locked account.
    import base64

    monkeypatch.setattr(settings, "keks", f"{version}:{base64.urlsafe_b64encode(bytes([7]) * 32).decode()}")
    from src.services.users import login

    assert login(identity.subject_hash(ISSUER, "sub-alice"), "sub-alice").locked


def test_a_ciphertext_copied_to_another_user_does_not_decrypt(alice, idp):
    bob = make_client(idp.token("sub-bob"))
    _ok(bob.get("/api/assets"))  # bob exists
    alice_ring, bob_ring = ring_for("sub-alice"), ring_for("sub-bob")
    cell = _blob("SELECT name FROM assets WHERE user_id = :u ORDER BY id DESC LIMIT 1", u=_uid(alice_ring.user_id))
    assert alice_ring.open("assets", "name", cell) == b"ZlotyHoardAsset"
    with pytest.raises(DecryptionError):
        bob_ring.open("assets", "name", cell)
    # Even with alice's data key itself, presented as bob: the user is in the AAD.
    with pytest.raises(DecryptionError):
        KeyRing(bob_ring.user_id, alice_ring.export_dek()).open("assets", "name", cell)


def test_a_ciphertext_copied_to_another_column_or_table_does_not_decrypt(alice):
    ring = ring_for("sub-alice")
    name = _blob("SELECT name FROM assets ORDER BY id DESC LIMIT 1")
    assert ring.open("assets", "name", name) == b"ZlotyHoardAsset"
    for table, column in (("assets", "category"), ("assets", "units"), ("expenses", "name"), ("settings", "value")):
        with pytest.raises(DecryptionError):
            ring.open(table, column, name)


def test_copying_a_cell_in_the_database_to_another_column_makes_the_read_fail_loudly(alice):
    """End to end rather than at the primitive: put one column's ciphertext into
    another with SQL, and the API refuses (500) instead of showing a wrong value."""
    with owner_engine().begin() as conn:
        conn.execute(text("UPDATE assets SET category = name WHERE name IS NOT NULL"))
    # The test client re-raises what the server would turn into a 500.
    with pytest.raises(DecryptionError):
        alice.get("/api/assets")


def test_known_limit_a_cell_swapped_between_two_rows_of_one_user_is_not_detected(alice):
    """Documented, not hidden: the cell types see one cell at a time and a new
    row's id does not exist until after its values are sealed, so a ciphertext is
    bound to its user, table and column but *not to its row*. Someone who can
    write to the database (and cannot read it) can swap two rows' values of one
    column; the application shows the swap. See README, 'What is not covered'."""
    c = alice
    second = _ok(c.post("/api/assets", json={"name": "ZlotySecond", "kind": "currency", "category": "x", "profile": "safe"}), 201)
    first_id = _ok(c.get("/api/assets"))[-2]["id"]
    with owner_engine().begin() as conn:
        a = conn.execute(text("SELECT name FROM assets WHERE id = :i"), {"i": first_id}).scalar()
        b = conn.execute(text("SELECT name FROM assets WHERE id = :i"), {"i": second["id"]}).scalar()
        conn.execute(text("UPDATE assets SET name = :n WHERE id = :i"), {"n": b, "i": first_id})
        conn.execute(text("UPDATE assets SET name = :n WHERE id = :i"), {"n": a, "i": second["id"]})
    names = {row["id"]: row["name"] for row in _ok(c.get("/api/assets"))}
    assert names[first_id] == "ZlotySecond" and names[second["id"]] == "ZlotyHoardAsset"


# --- sessions and keys -----------------------------------------------------------------------------------

def test_a_session_without_a_key_cannot_touch_an_encrypted_column(db):
    uid = db.info["user_id"]
    keyless = open_session(uid)
    try:
        with pytest.raises(KeysUnavailable):
            keyless.query(Setting).all()
        keyless.add(Setting(key="x", value="y"))
        with pytest.raises(StatementError) as raised:  # the driver-level wrapper around it
            keyless.commit()
        assert isinstance(raised.value.orig, KeysUnavailable)
    finally:
        keyless.rollback()
        keyless.close()
    # But it can still do what needs only plaintext columns.
    keyless = open_session(uid)
    try:
        assert keyless.execute(select(Setting.key)).all()
    finally:
        keyless.close()


def test_the_system_session_cannot_decrypt(db):
    db.add(Setting(key="secret-thing", value="hunter2"))
    db.commit()
    s = system_session()
    try:
        with pytest.raises(KeysUnavailable):
            s.query(Setting).all()
        assert ("secret-thing",) in s.execute(select(Setting.key)).all()
    finally:
        s.close()


def test_a_session_uses_its_own_key_whatever_else_is_in_force(db):
    """The key in force is the session's, not an ambient one: another user's key
    made current around the call changes nothing."""
    db.add(Setting(key="mine", value="mine"))
    db.commit()
    stranger = KeyRing(uuid.uuid4(), bytes(32))
    with activated(stranger):
        assert db.query(Setting).filter(Setting.key == "mine").one().value == "mine"


def test_a_result_is_decrypted_inside_the_call_not_lazily_afterwards(db):
    for i in range(3):
        db.add(Setting(key=f"k{i}", value=f"v{i}"))
    db.commit()
    keys = ["k0", "k1", "k2"]
    rows = db.execute(select(Setting.value).where(Setting.key.in_(keys)).order_by(Setting.key))
    # Consumed after execute() returned - outside any key context - and still fine,
    # because the rows were built under the session's key.
    assert [r[0] for r in rows] == ["v0", "v1", "v2"]
    query = db.query(Setting).filter(Setting.key.in_(keys)).order_by(Setting.key)
    assert [s.value for s in query] == ["v0", "v1", "v2"]


def test_an_expired_key_ring_stops_the_session(db):
    expired = KeyRing(db.info["user_id"], db.info[KEYRING_KEY].export_dek(), expires_at=1.0)
    s = SessionLocal(info={"user_id": db.info["user_id"], KEYRING_KEY: expired})
    try:
        with pytest.raises(KeyExpired):
            s.query(Setting).all()
    finally:
        s.close()


def test_a_session_for_one_user_refuses_another_users_key_ring(db):
    with pytest.raises(ValueError):
        open_session(uuid.uuid4(), db.info[KEYRING_KEY])


# --- values come back as the Python types the models declare --------------------------------------------------------

def test_values_survive_the_database_with_their_types(db):
    from datetime import date

    a = Asset(name="Ünïcode ✓", kind="currency", category="Cash", profile="safe")
    db.add(a)
    db.flush()
    db.add_all([
        Position(asset_id=a.id, amount=Decimal("1234.567891"), currency="PLN", value_in_base=1.005, price_used=0.1,
                 base_currency="PLN", flow_in_base=None, notes=""),
        Expense(name="E", amount=1.005, currency="PLN", period="monthly", category="", starts_on=date(2026, 3, 5),
                ends_on=None, notes="n"),
        Report(style="balanced", language="en", status="done", content="# c", snapshot={"k": [1, 2.5, None]}),
    ])
    db.commit()
    db.expire_all()
    p = db.query(Position).one()
    assert p.amount == Decimal("1234.567891") and isinstance(p.amount, Decimal)
    assert p.value_in_base == Decimal("1.0050") and p.flow_in_base is None
    e = db.query(Expense).one()
    assert e.amount == Decimal("1.01") and e.starts_on == date(2026, 3, 5) and e.ends_on is None
    r = db.query(Report).one()
    assert r.snapshot == {"k": [1, 2.5, None]} and r.error == ""
    assert db.query(Asset).one().name == "Ünïcode ✓"


def test_birth_year_is_optional_validated_and_encrypted(alice):
    assert _ok(alice.get("/api/settings"))["birth_year"] == 1987
    assert alice.put("/api/settings/birth-year", json={"birth_year": 1800}).status_code == 422
    assert alice.put("/api/settings/birth-year", json={"birth_year": 2999}).status_code == 422
    raw_year = raw("SELECT birth_year FROM users WHERE subject_hash = :h", h=identity.subject_hash(ISSUER, "sub-alice"))[0][0]
    assert bytes(raw_year)[:1] == b"\x01" and b"1987" not in bytes(raw_year)
    assert _ok(alice.put("/api/settings/birth-year", json={"birth_year": None}))["birth_year"] is None
    assert raw("SELECT birth_year FROM users WHERE subject_hash = :h", h=identity.subject_hash(ISSUER, "sub-alice"))[0][0] is None


def test_a_job_keyring_is_a_copy_and_destroyed_when_the_job_ends(alice, monkeypatch):
    """The queue gets the key from the request that queued the job and drops it
    when the job is over, however it ended; the request's own ring is untouched."""
    from src.routes import reports as reports_routes
    from src.services import llm

    seen = {}
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "## Summary\nok\n")
    real = reports_routes._generate

    def spy(ring, report_id):
        seen["ring"] = ring
        return real(ring, report_id)

    monkeypatch.setattr(reports_routes, "_generate", spy)
    r = _ok(alice.post("/api/reports", json={"style": "balanced", "language": "en"}), 202)
    import time

    deadline = time.time() + 5
    while time.time() < deadline and alice.get(f"/api/reports/{r['id']}").json()["status"] not in ("done", "failed"):
        time.sleep(0.02)
    assert alice.get(f"/api/reports/{r['id']}").json()["status"] == "done"
    assert seen["ring"].expired()  # destroyed after the job
    assert _ok(alice.get("/api/assets"))  # the request path is unaffected


def test_a_job_whose_key_allowance_ran_out_fails_with_a_note_instead_of_decrypting(alice, monkeypatch):
    from src.services import llm

    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "never reached")
    monkeypatch.setattr(settings, "job_key_seconds", -1)
    r = _ok(alice.post("/api/reports", json={"style": "balanced", "language": "en"}), 202)
    import time

    deadline = time.time() + 5
    got = {}
    while time.time() < deadline:
        got = alice.get(f"/api/reports/{r['id']}").json()
        if got["status"] in ("done", "failed"):
            break
        time.sleep(0.02)
    assert got["status"] == "failed" and "encryption key expired" in got["error"]
