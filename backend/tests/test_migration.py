"""The ownership and encryption migrations (src/schema.py, src/encmigrate.py): an
existing single-user database is converted in place, every row ends up owned by
the bootstrap user, and every value of theirs ends up encrypted under their key.

The "existing" database is built from the DDL the single-user models produced
(tests/fixtures/legacy_schema_*.sql), filled with dummy rows, and converted by
running `python -m src.schema` the way the Helm hook Job does - in a
subprocess, with the environment a deployment would set.

SQLite always runs. PostgreSQL runs when MYFINANCE_TEST_POSTGRES_URL points at a
scratch server (any database on it; a throwaway one is created and dropped per
test), e.g.

    MYFINANCE_TEST_POSTGRES_URL=postgresql+psycopg://user:pw@127.0.0.1:55432/postgres
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import MetaData, Table, create_engine, func, inspect, text
from sqlalchemy.orm import Session

from src import identity
from tests.fake_oidc import CONTACT_KEY, KEK_V2

BACKEND = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

ISSUER = "https://idp.test/realms/lab"
AUDIENCE = "myfinance-api"
PEPPER = "migration-test-pepper-0123456789abcdef"
BOOT_SUB = "the-original-owner-sub"

OWNED = [
    "assets", "positions", "expenses", "income_sources", "income_entries",
    "monthly_records", "insights", "reports", "settings",
]

# Owned by users too, but new in the encryption release: the legacy schema has no such table.
NEW_OWNED = ["user_contacts"]

POSTGRES_URL = os.environ.get("MYFINANCE_TEST_POSTGRES_URL")


# --- a database in the old shape -------------------------------------------

@pytest.fixture(params=["sqlite", pytest.param("postgresql", marks=pytest.mark.skipif(
    not POSTGRES_URL, reason="MYFINANCE_TEST_POSTGRES_URL not set"))])
def legacy_db(request, tmp_path):
    """(url, dialect) of a database holding the single-user schema, filled with
    dummy rows. Dropped afterwards."""
    dialect = request.param
    if dialect == "sqlite":
        url = f"sqlite:///{tmp_path}/legacy.db"
        cleanup = None
    else:
        admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
        name = f"mf_mig_{uuid.uuid4().hex[:10]}"
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        url = POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"

        def cleanup():
            with admin.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            admin.dispose()

    eng = create_engine(url)
    with eng.begin() as conn:
        for stmt in _ddl(dialect):
            conn.execute(text(stmt))
    _insert_dummy_rows(eng)
    eng.dispose()
    yield url, dialect
    if cleanup:
        cleanup()


def _ddl(dialect: str) -> list[str]:
    """The legacy statements, without the header comment."""
    out = []
    for chunk in (FIXTURES / f"legacy_schema_{dialect}.sql").read_text().split(";"):
        stmt = "\n".join(l for l in chunk.splitlines() if not l.startswith("--")).strip()
        if stmt:
            out.append(stmt)
    return out


def _insert_dummy_rows(eng) -> None:
    meta = MetaData()
    t = {n: Table(n, meta, autoload_with=eng) for n in OWNED}
    ts = datetime(2026, 5, 1, 10, 0, 0)
    with eng.begin() as conn:
        conn.execute(t["assets"].insert(), [
            dict(id=1, name="Cash", kind="currency", category="Cash", interest_basis="",
                 profile="safe", icon="", units="", wrapper="", created_at=ts, archived_at=None),
            dict(id=2, name="Gold", kind="gold", category="Gold", interest_basis="",
                 profile="moderate", icon="", units="g", wrapper="", created_at=ts, archived_at=None),
        ])
        conn.execute(t["positions"].insert(), [
            dict(id=1, asset_id=1, amount=Decimal("1000"), currency="PLN", value_in_base=Decimal("1000"),
                 price_used=Decimal("1"), base_currency="PLN", notes="a", accrues_from=None,
                 flow_in_base=None, timestamp=ts),
            dict(id=2, asset_id=1, amount=Decimal("1500"), currency="PLN", value_in_base=Decimal("1500"),
                 price_used=Decimal("1"), base_currency="PLN", notes="b", accrues_from=None,
                 flow_in_base=Decimal("500"), timestamp=datetime(2026, 6, 1)),
            dict(id=3, asset_id=2, amount=Decimal("10"), currency="PLN", value_in_base=Decimal("4000"),
                 price_used=Decimal("400"), base_currency="PLN", notes="", accrues_from=None,
                 flow_in_base=None, timestamp=ts),
        ])
        conn.execute(t["expenses"].insert(), [
            dict(id=1, name="Rent", amount=Decimal("2500"), currency="PLN", period="monthly",
                 category="Housing", starts_on=date(2026, 1, 1), ends_on=None, notes="", created_at=ts),
            dict(id=2, name="Holiday", amount=Decimal("4000"), currency="PLN", period="once",
                 category="Travel", starts_on=date(2026, 8, 1), ends_on=None, notes="", created_at=ts),
        ])
        conn.execute(t["income_sources"].insert(), [
            dict(id=1, name="Job", kind="uop", currency="PLN", params={"gross_monthly": 10000},
                 starts_on=date(2026, 1, 1), ends_on=None, notes="", created_at=ts),
        ])
        conn.execute(t["income_entries"].insert(), [
            dict(id=1, source_id=1, month="2026-03", amount=Decimal("12000"), units=None,
                 costs=Decimal("0"), override_net=None, notes="bonus", updated_at=ts),
            dict(id=2, source_id=1, month="2026-04", amount=Decimal("10000"), units=None,
                 costs=Decimal("0"), override_net=Decimal("7000"), notes="", updated_at=ts),
        ])
        conn.execute(t["monthly_records"].insert(), [
            dict(id=1, month="2026-03", income=Decimal("9000"), actual_spent=Decimal("5000"),
                 currency="PLN", notes="", commitments_paid=None, other_spent=None, updated_at=ts),
            dict(id=2, month="2026-04", income=Decimal("9000"), actual_spent=Decimal("5200"),
                 currency="PLN", notes="", commitments_paid="[]", other_spent=Decimal("0"), updated_at=ts),
        ])
        conn.execute(t["insights"].insert(), [
            dict(id=1, created_at=ts, kind="digest", period="2026-03", status="done", language="en",
                 content="# text", content_en="# text", data={}, data_localized=None, snapshot={"a": 1},
                 ungrounded=[], model="m", translator="", error=""),
        ])
        conn.execute(t["reports"].insert(), [
            dict(id=1, created_at=ts, status="done", style="balanced", language="en", content="# r",
                 content_en="# r", model="m", translator="", error="", snapshot={"b": 2}),
        ])
        conn.execute(t["settings"].insert(), [
            dict(key="base_currency", value="EUR"),
            dict(key="features", value=json.dumps(
                {"portfolio": True, "fire": True, "tax": True, "insights": True})),
            dict(key="terms_accepted", value=json.dumps(
                {"version": 1, "accepted_at": "2026-05-01T10:00:00+00:00"})),
            dict(key="fire", value=json.dumps({"birth_year": 1990})),
        ])


def _run_schema(url: str, **env) -> subprocess.CompletedProcess:
    e = {k: v for k, v in os.environ.items() if not k.startswith("MYFINANCE_")}
    e["MYFINANCE_DATABASE_URL"] = url
    e["MYFINANCE_DATA_DIR"] = str(Path(url.split("///")[-1]).parent) if url.startswith("sqlite") else "/tmp"
    e.update(env)
    return subprocess.run(
        [sys.executable, "-m", "src.schema"], cwd=str(BACKEND), env=e,
        capture_output=True, text=True,
    )


AUTH_ENV = dict(
    MYFINANCE_AUTH_ISSUER=ISSUER,
    MYFINANCE_AUTH_AUDIENCE=AUDIENCE,
    MYFINANCE_AUTH_REQUIRE_AT_JWT_TYP="true",
    MYFINANCE_SUBJECT_PEPPER=PEPPER,
    MYFINANCE_BOOTSTRAP_SUB=BOOT_SUB,
    # Authentication on means encryption on: the KEK and the contact key are mandatory.
    MYFINANCE_KEKS=f"2:{KEK_V2}",
    MYFINANCE_CONTACT_KEY=CONTACT_KEY,
)

# Strings and figures the legacy dummy rows hold. After the migration none of
# them may appear in the clear anywhere in an encrypted column.
PLAINTEXT_MARKERS = [
    "Cash", "Gold", "Rent", "Holiday", "Housing", "Travel", "bonus", "gross_monthly", "balanced",
    "# text", "1000", "1500", "4000", "12000", "10000", "9000", "5200", "2500", "7000", "2026-01-01",
]


def _boot_ring(eng, secret: str = BOOT_SUB, keks="env"):
    """The bootstrap user's key ring, unwrapped from the database the way their
    next sign-in will do it. `keks=None`: the public development KEK."""
    from src.crypto.core import DEV_KEK_VERSION, KekSet, KeyRing, _DEV_KEK, parse_keks, unwrap_dek

    with eng.connect() as c:
        uid, salt, wrapped, version = c.execute(
            text("SELECT id, key_salt, wrapped_dek, kek_version FROM users")
        ).one()
    uid = uuid.UUID(str(uid))
    keks = parse_keks(AUTH_ENV["MYFINANCE_KEKS"]) if keks == "env" else KekSet({DEV_KEK_VERSION: _DEV_KEK}, DEV_KEK_VERSION)
    dek = unwrap_dek(wrapped, user_id=uid, kek=keks.get(version), kek_version=version,
                     salt=salt, secret=secret)
    return KeyRing(uid, dek)


def _encrypted_cells(eng) -> list[tuple[str, str, bytes | None]]:
    """(table, column, raw stored value) for every encrypted column, read as the
    database holds it - no key, no type processing."""
    from src import models  # noqa: F401  (registers the tables on Base)
    from src.crypto.fields import encrypted_columns
    from src.database import Base

    out = []
    with eng.connect() as c:
        for table in Base.metadata.sorted_tables:
            for col, _ in encrypted_columns(table):
                if table.name == "users":
                    continue
                for (v,) in c.execute(text(f'SELECT "{col.name}" FROM "{table.name}"')):
                    out.append((table.name, col.name, None if v is None else bytes(v)))
    return out


def _insert_sealed(conn, ring, table_name: str, **values) -> None:
    """Insert one row, sealing its encrypted columns under `ring` - what a user's
    own request would store."""
    from sqlalchemy import insert

    from src import encmigrate, models  # noqa: F401  (registers the tables on Base)
    from src.crypto.fields import Encrypted
    from src.database import Base

    t = Base.metadata.tables[table_name]
    row = {
        k: t.c[k].type.seal_with(ring, v) if isinstance(t.c[k].type, Encrypted) else v
        for k, v in values.items()
    }
    conn.execute(insert(encmigrate.raw_view(t)), [row])


def _counts(eng) -> dict[str, int]:
    with eng.connect() as c:
        return {n: c.execute(text(f'SELECT count(*) FROM "{n}"')).scalar() for n in OWNED}


def _read_as_owner(url: str, ring, check) -> None:
    """Run `check(session)` on a session for the bootstrap user, over the
    database at `url`, holding their key ring (bypassing the module-level engine,
    which points at whatever the test process was started with)."""
    from src.database import KEYRING_KEY, KeyedSession

    eng = create_engine(url)
    try:
        with KeyedSession(eng, info={"user_id": ring.user_id, KEYRING_KEY: ring}) as db:
            check(db)
    finally:
        eng.dispose()


def _assert_dummy_rows_intact(db) -> None:
    from src.models import Asset, Expense, IncomeEntry, IncomeSource, Insight, MonthlyRecord, Position, Report, Setting

    positions = db.query(Position).order_by(Position.id).all()
    assert [(p.id, p.asset_id, p.amount, p.currency, p.notes) for p in positions] == [
        (1, 1, Decimal("1000"), "PLN", "a"),
        (2, 1, Decimal("1500"), "PLN", "b"),
        (3, 2, Decimal("10"), "PLN", ""),
    ]
    assert [p.flow_in_base for p in positions] == [None, Decimal("500"), None]
    assert positions[1].price_used == Decimal("1") and positions[2].value_in_base == Decimal("4000")
    assets = db.query(Asset).order_by(Asset.id).all()
    assert [(a.name, a.kind, a.category, a.profile, a.units) for a in assets] == [
        ("Cash", "currency", "Cash", "safe", ""), ("Gold", "gold", "Gold", "moderate", "g"),
    ]
    expenses = db.query(Expense).order_by(Expense.id).all()
    assert [(e.name, e.amount, e.period, e.category, e.starts_on, e.ends_on) for e in expenses] == [
        ("Rent", Decimal("2500"), "monthly", "Housing", date(2026, 1, 1), None),
        ("Holiday", Decimal("4000"), "once", "Travel", date(2026, 8, 1), None),
    ]
    (source,) = db.query(IncomeSource).all()
    assert source.params == {"gross_monthly": 10000} and source.kind == "uop"
    entries = db.query(IncomeEntry).order_by(IncomeEntry.id).all()
    assert [(e.month, e.amount, e.notes, e.override_net) for e in entries] == [
        ("2026-03", Decimal("12000"), "bonus", None), ("2026-04", Decimal("10000"), "", Decimal("7000")),
    ]
    records = db.query(MonthlyRecord).order_by(MonthlyRecord.id).all()
    assert [(r.month, r.income, r.actual_spent, r.commitments_paid, r.other_spent) for r in records] == [
        ("2026-03", Decimal("9000"), Decimal("5000"), None, None),
        ("2026-04", Decimal("9000"), Decimal("5200"), "[]", Decimal("0")),
    ]
    (insight,) = db.query(Insight).all()
    assert (insight.content, insight.snapshot, insight.data, insight.data_localized, insight.ungrounded) == (
        "# text", {"a": 1}, {}, None, [])
    (report,) = db.query(Report).all()
    assert (report.style, report.content, report.snapshot, report.error) == ("balanced", "# r", {"b": 2}, "")
    settings_rows = {s.key: s.value for s in db.query(Setting).all()}
    assert settings_rows["base_currency"] == "EUR"
    assert json.loads(settings_rows["fire"]) == {"birth_year": 1990}


def test_the_migrated_values_are_ciphertext_in_the_database(legacy_db):
    """Raw SQL, no key: not one of the legacy strings or figures is in the clear
    in any encrypted column, and every cell is a sealed blob."""
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    cells = _encrypted_cells(eng)
    assert len(cells) >= 90
    for table, column, value in cells:
        if value is None:
            continue
        assert value[:1] == b"\x01", (table, column)  # format version, then the nonce
        for marker in PLAINTEXT_MARKERS:
            assert marker.encode() not in value, (table, column, marker)
    # Column types really changed, not just their contents.
    insp = inspect(eng)
    from sqlalchemy.types import _Binary

    for table, column in (("positions", "amount"), ("assets", "name"), ("expenses", "starts_on"),
                          ("settings", "value"), ("reports", "content"), ("insights", "snapshot")):
        col = next(c for c in insp.get_columns(table) if c["name"] == column)
        assert isinstance(col["type"], _Binary), (table, column, col["type"])
    eng.dispose()


def test_the_bootstrap_users_key_is_the_one_their_sign_in_derives(legacy_db):
    """The migration creates the key from MYFINANCE_BOOTSTRAP_SUB exactly as a
    login will: so signing in as that person unlocks the migrated data. And the
    DB plus the KEK are not enough: another `sub` does not open it."""
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    from src.crypto.core import DecryptionError

    ring = _boot_ring(eng)
    assert ring.user_id
    with pytest.raises(DecryptionError):
        _boot_ring(eng, secret="some-other-sub")
    eng.dispose()


# --- the migration -------------------------------------------------------------

def test_existing_rows_are_assigned_to_the_bootstrap_user(legacy_db):
    url, dialect = legacy_db
    eng = create_engine(url)
    before = _counts(eng)
    assert before["positions"] == 3 and before["settings"] == 4

    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    # The raw sub is never printed.
    assert BOOT_SUB not in result.stdout + result.stderr

    # Nothing lost, nothing added.
    after = _counts(eng)
    assert after == {**before, "settings": 3}  # terms_accepted moved to the user

    # Exactly one user, whose hash is what that person's login will compute.
    with eng.connect() as c:
        users = c.execute(text("SELECT id, subject_hash, terms_version FROM users")).all()
    assert len(users) == 1
    owner_id, digest, terms_version = users[0]
    assert digest == identity.subject_hash(ISSUER, BOOT_SUB, pepper=PEPPER)
    assert terms_version == 1

    # Every row of every data table is theirs.
    with eng.connect() as c:
        for name in OWNED:
            owners = {str(r[0]).replace("-", "") for r in c.execute(text(f'SELECT DISTINCT user_id FROM "{name}"'))}
            assert owners == {str(owner_id).replace("-", "")}, name

    # ... and the data came across intact: decrypted with the owner's key it is
    # exactly what was there, with its Python types (Decimal, date, parsed JSON).
    ring = _boot_ring(eng)
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM settings WHERE key = 'terms_accepted'")).scalar() == 0
        assert c.execute(text("SELECT terms_accepted_at FROM users")).scalar() is not None
    eng.dispose()
    _read_as_owner(url, ring, lambda db: _assert_dummy_rows_intact(db))


def test_schema_after_migration_has_the_new_constraints(legacy_db):
    url, dialect = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    insp = inspect(eng)

    for name in OWNED:
        cols = {c["name"]: c for c in insp.get_columns(name)}
        assert cols["user_id"]["nullable"] is False, name
        fks = [fk for fk in insp.get_foreign_keys(name) if fk["constrained_columns"] == ["user_id"]]
        assert fks and fks[0]["referred_table"] == "users", name

    assert insp.get_pk_constraint("settings")["constrained_columns"] == ["user_id", "key"]

    def uniques(table):
        found = [tuple(u["column_names"]) for u in insp.get_unique_constraints(table)]
        found += [tuple(i["column_names"]) for i in insp.get_indexes(table) if i.get("unique")]
        return found

    assert ("user_id", "month") in uniques("monthly_records")
    assert ("month",) not in uniques("monthly_records")
    assert ("user_id", "source_id", "month") in uniques("income_entries")
    assert ("source_id", "month") not in uniques("income_entries")

    # The user_id index survived the rebuild (SQLite recreates every table); the
    # indexes on columns that are ciphertext now (category, profile) are gone -
    # an index over random bytes is a cost and no use.
    asset_indexes = {i["name"] for i in insp.get_indexes("assets")}
    assert "ix_assets_user_id" in asset_indexes
    assert not {"ix_assets_category", "ix_assets_profile"} & asset_indexes

    # Per-user uniqueness works in practice: a second user may have the same
    # month, the same user may not.
    with eng.begin() as conn:
        owner = conn.execute(text("SELECT id FROM users")).scalar()
        other = uuid.uuid4()
        conn.execute(
            text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, :t)")
            .bindparams(i=other if dialect == "postgresql" else other.hex, h="f" * 64, t=datetime(2026, 1, 1))
        )
        other_param = other if dialect == "postgresql" else other.hex
        owner_param = owner if dialect == "postgresql" else str(owner)
        from src.crypto.core import KeyRing, new_dek

        ring = KeyRing(other, new_dek())

        def record(row_id):
            _insert_sealed(
                conn, ring, "monthly_records", id=row_id, user_id=other, month="2026-03",
                income=1, actual_spent=1, currency="PLN", notes="", updated_at=datetime(2026, 1, 1),
            )

        record(100)
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            record(101)
    eng.dispose()


def _fingerprint(eng) -> dict:
    insp = inspect(eng)
    out = {}
    for t in sorted(insp.get_table_names()):
        out[t] = {
            "columns": sorted((c["name"], c["nullable"]) for c in insp.get_columns(t)),
            "pk": insp.get_pk_constraint(t)["constrained_columns"],
            "fks": sorted(
                (tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]))
                for f in insp.get_foreign_keys(t)
            ),
            "uniques": sorted(
                (u["name"], tuple(u["column_names"])) for u in insp.get_unique_constraints(t)
            ),
            "indexes": sorted(
                (i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(t)
            ),
        }
    return out


def test_a_migrated_database_has_the_same_schema_as_a_fresh_one(legacy_db, tmp_path):
    url, dialect = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0

    if dialect == "sqlite":
        fresh_url, cleanup = f"sqlite:///{tmp_path}/fresh.db", None
    else:
        admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
        name = f"mf_fresh_{uuid.uuid4().hex[:10]}"
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{name}"'))
        fresh_url = POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"

        def cleanup():
            with admin.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            admin.dispose()

    try:
        assert _run_schema(fresh_url).returncode == 0
        migrated, fresh = create_engine(url), create_engine(fresh_url)
        assert _fingerprint(migrated) == _fingerprint(fresh)
        migrated.dispose()
        fresh.dispose()
    finally:
        if cleanup:
            cleanup()


def test_the_migrated_database_is_served_to_the_bootstrap_user_only(legacy_db):
    """Through the ORM, the way the application reads it."""
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0

    from src.database import KEYRING_KEY, KeyedSession
    from src.models import Asset, Expense, Position, Setting
    from src.crypto.core import KeyRing, new_dek

    eng = create_engine(url)
    ring = _boot_ring(eng)
    with KeyedSession(eng, info={"user_id": ring.user_id, KEYRING_KEY: ring}) as mine:
        assert {a.name for a in mine.query(Asset).all()} == {"Cash", "Gold"}
        assert mine.query(func.count(Position.id)).scalar() == 3
        assert mine.query(Setting).filter(Setting.key == "base_currency").one().value == "EUR"
        assert mine.query(func.count(Expense.id)).scalar() == 2
    stranger_id = uuid.uuid4()
    with KeyedSession(
        eng, info={"user_id": stranger_id, KEYRING_KEY: KeyRing(stranger_id, new_dek())}
    ) as stranger:
        assert stranger.query(Asset).all() == []
        assert stranger.query(Setting).all() == []
    eng.dispose()


def test_a_second_run_changes_nothing(legacy_db):
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    snapshot = _counts(eng)
    cells = _encrypted_cells(eng)
    with eng.connect() as c:
        users_before = c.execute(text(
            "SELECT id, subject_hash, key_salt, wrapped_dek, kek_version FROM users")).all()

    again = _run_schema(url, **AUTH_ENV)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "ownership" not in again.stdout and "encrypted:" not in again.stdout
    assert _counts(eng) == snapshot
    # Byte-for-byte the same: a second run did not re-encrypt anything (a fresh
    # nonce would change every cell) and did not touch the user's key.
    assert _encrypted_cells(eng) == cells
    with eng.connect() as c:
        assert c.execute(text(
            "SELECT id, subject_hash, key_salt, wrapped_dek, kek_version FROM users")).all() == users_before
    eng.dispose()


def test_a_deployment_without_a_bootstrap_identity_is_refused_and_left_untouched(legacy_db):
    url, _ = legacy_db
    env = {k: v for k, v in AUTH_ENV.items() if k != "MYFINANCE_BOOTSTRAP_SUB"}
    result = _run_schema(url, **env)
    assert result.returncode == 1
    assert "MYFINANCE_BOOTSTRAP_SUB" in result.stderr

    eng = create_engine(url)
    assert "user_id" not in {c["name"] for c in inspect(eng).get_columns("positions")}
    assert _counts(eng)["positions"] == 3
    eng.dispose()


def test_bootstrap_without_a_pepper_is_refused(legacy_db):
    url, _ = legacy_db
    env = {k: v for k, v in AUTH_ENV.items() if k != "MYFINANCE_SUBJECT_PEPPER"}
    result = _run_schema(url, **env)
    assert result.returncode == 1
    assert "PEPPER" in result.stderr


def test_with_auth_off_existing_data_goes_to_the_local_user(legacy_db):
    url, _ = legacy_db
    result = _run_schema(url)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "local development user" in result.stdout
    assert "development KEK" in result.stdout  # said out loud: public key, protects nothing
    eng = create_engine(url)
    with eng.connect() as c:
        assert c.execute(text("SELECT subject_hash FROM users")).scalar() == identity.local_subject_hash()
    # Encrypted all the same, under the local user's key (constant secret, public KEK).
    from src.crypto.core import LOCAL_SECRET, DecryptionError

    ring = _boot_ring(eng, secret=LOCAL_SECRET, keks=None)
    assert ring.user_id == identity.LOCAL_USER_ID
    assert all(v is None or bytes(v)[:1] == b"\x01" for _, _, v in _encrypted_cells(eng))
    _read_as_owner(url, ring, _assert_dummy_rows_intact)
    eng.dispose()


# --- plaintext that must not be encrypted under a guess ---------------------------------------------------

_UP_TO_ENCRYPTION = """
from src import auth, schema
from src.database import Base, engine
auth.validate_config()
Base.metadata.create_all(bind=engine)
schema.migrate()
schema.record_key_checks()
schema.migrate_ownership()
schema.migrate_integrity()
schema.move_terms_to_users()
"""


def _phase_two(url: str, **env) -> None:
    """Bring a legacy database to how the previous release left it: ownership
    done, every value still plaintext. (The schema job minus its last data step.)"""
    e = {k: v for k, v in os.environ.items() if not k.startswith("MYFINANCE_")}
    e.update(MYFINANCE_DATABASE_URL=url, MYFINANCE_DATA_DIR="/tmp", **(env or AUTH_ENV))
    r = subprocess.run([sys.executable, "-c", _UP_TO_ENCRYPTION], cwd=str(BACKEND), env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _is_plain(eng) -> bool:
    from sqlalchemy.types import _Binary

    return not any(
        isinstance(c["type"], _Binary)
        for c in inspect(eng).get_columns("positions") if c["name"] == "amount"
    )


def test_plaintext_rows_of_anyone_but_the_bootstrap_user_stop_the_migration_and_are_named(legacy_db):
    url, dialect = legacy_db
    _phase_two(url)
    eng = create_engine(url)
    stranger = uuid.uuid4()
    with eng.begin() as c:
        c.execute(text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, :t)"),
                  {"i": stranger if dialect == "postgresql" else stranger.hex, "h": "7" * 64, "t": datetime(2026, 1, 1)})
        c.execute(text(
            "INSERT INTO assets (id, user_id, name, kind, category, interest_basis, profile, icon, units, wrapper, created_at) "
            "VALUES (70, :u, 'Strangers asset', 'currency', 'Cash', '', 'safe', '', '', '', :t)"),
            {"u": stranger if dialect == "postgresql" else stranger.hex, "t": datetime(2026, 1, 1)})
    before = _counts(eng)
    assert _is_plain(eng)

    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 1, result.stdout + result.stderr
    # Named: whose rows, and where. Not guessed, not skipped.
    assert str(stranger) in result.stderr and "assets=1" in result.stderr
    assert "other than the bootstrap user" in result.stderr
    # ... and nothing was changed: still plaintext, still the same rows, no key made.
    assert _is_plain(eng) and _counts(eng) == before
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users WHERE wrapped_dek IS NOT NULL")).scalar() == 0
        assert c.execute(text("SELECT name FROM assets WHERE id = 70")).scalar() == "Strangers asset"
    eng.dispose()


def test_a_stranger_with_no_data_is_left_alone_and_gets_a_key_at_their_first_sign_in(legacy_db):
    url, dialect = legacy_db
    _phase_two(url)
    eng = create_engine(url)
    idle = uuid.uuid4()
    with eng.begin() as c:
        c.execute(text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, :t)"),
                  {"i": idle if dialect == "postgresql" else idle.hex, "h": "6" * 64, "t": datetime(2026, 1, 1)})
    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    with eng.connect() as c:
        keyed = dict(c.execute(text("SELECT subject_hash, wrapped_dek IS NOT NULL FROM users")).all())
    assert keyed["6" * 64] in (0, False) and keyed[identity.subject_hash(ISSUER, BOOT_SUB, pepper=PEPPER)] in (1, True)
    eng.dispose()


def test_a_wrong_bootstrap_sub_stops_the_migration_untouched(legacy_db):
    url, _ = legacy_db
    _phase_two(url)
    eng = create_engine(url)
    before = _counts(eng)
    result = _run_schema(url, **{**AUTH_ENV, "MYFINANCE_BOOTSTRAP_SUB": "somebody-else"})
    assert result.returncode == 1 and "bootstrap identity" in result.stderr
    assert _is_plain(eng) and _counts(eng) == before
    eng.dispose()


def test_an_existing_key_that_the_bootstrap_sub_does_not_open_stops_the_migration(legacy_db):
    """The user already has a data key (so a sign-in has been through) but the
    configured sub is not the one it was wrapped with: encrypting more data under a
    different key would split their data across two keys. Refused, by name."""
    url, dialect = legacy_db
    _phase_two(url)
    eng = create_engine(url)
    from src.crypto.core import new_dek, new_salt, parse_keks, wrap_dek

    with eng.connect() as c:
        uid = c.execute(text("SELECT id FROM users")).scalar()
    keks = parse_keks(AUTH_ENV["MYFINANCE_KEKS"])
    salt = new_salt()
    wrapped = wrap_dek(new_dek(), user_id=uuid.UUID(str(uid)), kek=keks.current_key, kek_version=2, salt=salt, secret="another-sub")
    with eng.begin() as c:
        c.execute(text("UPDATE users SET key_salt = :s, wrapped_dek = :w, kek_version = 2"), {"s": salt, "w": wrapped})
    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 1 and "does not open" in result.stderr
    assert _is_plain(eng)
    eng.dispose()


def test_a_wrong_kek_stops_the_schema_job_before_it_writes_anything(legacy_db):
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    cells = _encrypted_cells(eng)
    users = None
    with eng.connect() as c:
        users = c.execute(text("SELECT id, subject_hash, wrapped_dek FROM users")).all()
    import base64

    wrong = base64.urlsafe_b64encode(os.urandom(32)).decode()
    result = _run_schema(url, **{**AUTH_ENV, "MYFINANCE_KEKS": f"2:{wrong}"})
    assert result.returncode == 1
    assert "KEK version 2 does not open the key-check value" in result.stderr
    assert "Nothing has been written" in result.stderr
    assert _encrypted_cells(eng) == cells
    with eng.connect() as c:
        assert c.execute(text("SELECT id, subject_hash, wrapped_dek FROM users")).all() == users
    eng.dispose()


def test_a_database_with_users_on_a_kek_that_is_no_longer_listed_stops_the_schema_job(legacy_db):
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    from tests.fake_oidc import KEK_V3

    result = _run_schema(url, **{**AUTH_ENV, "MYFINANCE_KEKS": f"3:{KEK_V3}"})
    assert result.returncode == 1 and "v2 (1 user)" in result.stderr


def test_a_failure_part_way_through_encrypting_leaves_the_plaintext_intact(legacy_db, monkeypatch):
    """Transactional on both databases: an error after some tables were converted
    rolls all of it back - old types, old plaintext, no key stored."""
    url, _ = legacy_db
    _phase_two(url)
    eng = create_engine(url)
    before = _counts(eng)

    from src import encmigrate
    from src.config import settings

    for name, value in (("auth_issuer", ISSUER), ("auth_audience", AUDIENCE), ("auth_require_at_jwt_typ", True),
                        ("subject_pepper", PEPPER), ("bootstrap_sub", BOOT_SUB),
                        ("keks", AUTH_ENV["MYFINANCE_KEKS"]), ("contact_key", CONTACT_KEY)):
        monkeypatch.setattr(settings, name, value)
    real = encmigrate._convert_rows
    calls = {"n": 0}

    def flaky(p, rows, keys):
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("boom")
        return real(p, rows, keys)

    monkeypatch.setattr(encmigrate, "_convert_rows", flaky)
    with pytest.raises(RuntimeError, match="boom"):
        encmigrate.migrate_encryption(eng)
    assert calls["n"] == 4
    assert _is_plain(eng) and _counts(eng) == before
    insp = inspect(eng)
    assert not [t for t in insp.get_table_names() if t.endswith("__plain")]
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users WHERE wrapped_dek IS NOT NULL")).scalar() == 0
        assert c.execute(text("SELECT name FROM assets WHERE id = 1")).scalar() == "Cash"
    eng.dispose()

    # And the same run, un-sabotaged, then succeeds from that state.
    monkeypatch.setattr(encmigrate, "_convert_rows", real)
    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_key_claim_other_than_sub_needs_its_own_bootstrap_value(legacy_db):
    url, _ = legacy_db
    _phase_two(url)
    env = {**AUTH_ENV, "MYFINANCE_KEY_CLAIM": "uid"}
    refused = _run_schema(url, **env)
    assert refused.returncode == 1 and "MYFINANCE_BOOTSTRAP_KEY_SECRET" in refused.stderr
    ok = _run_schema(url, **env, MYFINANCE_BOOTSTRAP_KEY_SECRET="the-uid-claim-value")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "the-uid-claim-value" not in ok.stdout + ok.stderr
    eng = create_engine(url)
    ring = _boot_ring(eng, secret="the-uid-claim-value")
    _read_as_owner(url, ring, _assert_dummy_rows_intact)
    from src.crypto.core import DecryptionError

    with pytest.raises(DecryptionError):
        _boot_ring(eng, secret=BOOT_SUB)  # the sub is not what unlocks it here
    eng.dispose()


def test_an_empty_legacy_database_is_converted_without_inventing_a_user(legacy_db):
    url, _ = legacy_db
    eng = create_engine(url)
    with eng.begin() as conn:
        for name in ("positions", "income_entries", "assets", "expenses", "income_sources",
                     "monthly_records", "insights", "reports", "settings"):
            conn.execute(text(f'DELETE FROM "{name}"'))
    # No data and no bootstrap settings: nothing to ask the operator.
    env = {k: v for k, v in AUTH_ENV.items() if k != "MYFINANCE_BOOTSTRAP_SUB"}
    result = _run_schema(url, **env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "user_id" in {c["name"] for c in inspect(eng).get_columns("positions")}
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 0
    eng.dispose()


def test_a_fresh_database_gets_ownership_from_create_all(tmp_path):
    url = f"sqlite:///{tmp_path}/fresh.db"
    result = _run_schema(url)
    assert result.returncode == 0, result.stdout + result.stderr
    eng = create_engine(url)
    insp = inspect(eng)
    assert "users" in insp.get_table_names()
    for name in OWNED:
        assert "user_id" in {c["name"] for c in insp.get_columns(name)}
    eng.dispose()


def test_users_table_holds_no_personal_data_columns(tmp_path):
    url = f"sqlite:///{tmp_path}/fresh.db"
    assert _run_schema(url).returncode == 0
    eng = create_engine(url)
    cols = {c["name"] for c in inspect(eng).get_columns("users")}
    assert cols == {
        "id", "subject_hash", "created_at", "terms_version", "terms_accepted_at",
        # per-user encryption: wrapped key and its recovery copy (no name, e-mail or id)
        "key_salt", "wrapped_dek", "kek_version",
        "recovery_id", "recovery_salt", "recovery_kdf", "recovery_wrapped_dek", "recovery_verifier",
        "recovery_created_at", "recovery_confirmed_at", "recovery_failures", "recovery_locked_until",
        "birth_year",
    }
    eng.dispose()


def test_failure_part_way_leaves_the_old_schema_intact(tmp_path, monkeypatch):
    """SQLite DDL is made transactional by an explicit BEGIN; an error after
    some tables were rebuilt must roll all of it back."""
    url = f"sqlite:///{tmp_path}/legacy.db"
    eng = create_engine(url)
    with eng.begin() as conn:
        for stmt in _ddl("sqlite"):
            conn.execute(text(stmt))
    _insert_dummy_rows(eng)
    before = _counts(eng)

    from src import schema
    from src.config import settings
    from src.database import Base  # noqa: F401
    from src.models.user import User

    # `users` is made by create_all in main(); do the same here.
    User.__table__.create(eng)
    for name, value in (("auth_issuer", ISSUER), ("auth_audience", AUDIENCE),
                        ("subject_pepper", PEPPER), ("bootstrap_sub", BOOT_SUB)):
        monkeypatch.setattr(settings, name, value)

    real = schema._owner_param
    calls = {"n": 0}

    def flaky(owner):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return real(owner)

    monkeypatch.setattr(schema, "_owner_param", flaky)
    with pytest.raises(RuntimeError, match="boom"):
        schema.migrate_ownership(eng)

    insp = inspect(eng)
    for name in OWNED:
        assert "user_id" not in {c["name"] for c in insp.get_columns(name)}, name
    assert not [t for t in insp.get_table_names() if t.endswith("__premulti")]
    assert _counts(eng) == before
    with eng.connect() as c:
        assert c.execute(text("SELECT count(*) FROM users")).scalar() == 0
    eng.dispose()


# --- row-level security and composite keys: PostgreSQL ---------------------------------------

RUNTIME_URL = (
    os.environ.get("MYFINANCE_TEST_DATABASE_URL")
    if os.environ.get("MYFINANCE_TEST_OWNER_DATABASE_URL") else None
)


def _pg_only(dialect: str) -> None:
    if dialect != "postgresql":
        pytest.skip("PostgreSQL only")


def _catalog(eng) -> dict:
    """Everything row-level security and the composite keys add, as the catalog
    sees it, in a form two databases can be compared by."""
    with eng.connect() as c:
        def rows(sql):
            return [tuple(r) for r in c.execute(text(sql))]

        return {
            "policies": rows(
                "SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check "
                "FROM pg_policies ORDER BY 1, 2"),
            "flags": rows(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = 'public'::regnamespace AND relkind = 'r' ORDER BY 1"),
            "functions": rows(
                "SELECT proname, prosecdef, md5(prosrc), proconfig::text, proacl::text FROM pg_proc "
                "WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'myfinance_%' ORDER BY 1"),
            "constraints": rows(
                "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace AND contype IN ('u', 'f') ORDER BY 1, 2"),
        }


def _as_phase_one(eng) -> None:
    """Take a database the schema job has finished with back to how the
    previous release left it: user_id everywhere, but no row-level security, no
    functions, and plain single-column foreign keys for positions and
    income_entries."""
    with eng.begin() as c:
        for t in OWNED + NEW_OWNED + ["users"]:
            c.execute(text(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY'))
            c.execute(text(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY'))
        for (name, table) in c.execute(text("SELECT policyname, tablename FROM pg_policies")).all():
            c.execute(text(f'DROP POLICY "{name}" ON "{table}"'))
        c.execute(text("DROP FUNCTION public.myfinance_get_or_create_user(text, uuid, bytea, bytea, integer)"))
        for name, args in (("myfinance_recovery_lookup", "text"),
                           ("myfinance_recover_account", "text, bytea, bytea, bytea, integer"),
                           ("myfinance_contact_unsubscribe", "bytea")):
            c.execute(text(f"DROP FUNCTION public.{name}({args})"))
        c.execute(text("DROP FUNCTION public.myfinance_sweep_interrupted_jobs()"))
        c.execute(text("ALTER TABLE positions DROP CONSTRAINT fk_positions_user_asset"))
        c.execute(text("ALTER TABLE income_entries DROP CONSTRAINT fk_income_entries_user_source"))
        c.execute(text("ALTER TABLE assets DROP CONSTRAINT uq_assets_user_id_id"))
        c.execute(text("ALTER TABLE income_sources DROP CONSTRAINT uq_income_sources_user_id_id"))
        c.execute(text("ALTER TABLE positions ADD CONSTRAINT positions_asset_id_fkey "
                       "FOREIGN KEY (asset_id) REFERENCES assets (id)"))
        c.execute(text("ALTER TABLE income_entries ADD CONSTRAINT income_entries_source_id_fkey "
                       "FOREIGN KEY (source_id) REFERENCES income_sources (id)"))


def _fresh_pg(name_prefix="mf_fresh"):
    admin = create_engine(POSTGRES_URL, isolation_level="AUTOCOMMIT")
    name = f"{name_prefix}_{uuid.uuid4().hex[:10]}"
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    url = POSTGRES_URL.rsplit("/", 1)[0] + f"/{name}"

    def cleanup():
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()

    return url, cleanup


def test_the_schema_job_installs_row_security_and_a_second_run_changes_nothing(legacy_db):
    url, dialect = legacy_db
    _pg_only(dialect)
    first = _run_schema(url, **AUTH_ENV)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "row-level security" in first.stdout
    eng = create_engine(url)
    cat = _catalog(eng)
    assert {p[0] for p in cat["policies"]} == set(OWNED) | set(NEW_OWNED) | {"users"}
    assert all(f[1] and f[2] for f in cat["flags"] if f[0] in OWNED + NEW_OWNED + ["users"])
    names = {c[1] for c in cat["constraints"]}
    assert {"fk_positions_user_asset", "fk_income_entries_user_source"} <= names
    # The single-column foreign keys the composite ones replace are gone.
    assert not {"positions_asset_id_fkey", "income_entries_source_id_fkey"} & names

    again = _run_schema(url, **AUTH_ENV)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "composite" not in again.stdout and "ownership" not in again.stdout
    assert _catalog(eng) == cat
    eng.dispose()


def test_a_phase_one_database_is_upgraded_and_ends_up_like_a_fresh_one(legacy_db):
    """Phase one: user_id on every table, several users, no row-level security."""
    url, dialect = legacy_db
    _pg_only(dialect)
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    _as_phase_one(eng)
    # A second user with data of their own - what phase one allowed.
    with eng.begin() as c:
        other = uuid.uuid4()
        c.execute(text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, now())"),
                  {"i": other, "h": "9" * 64})
        from src.crypto.core import KeyRing, new_dek

        ring = KeyRing(other, new_dek())
        _insert_sealed(c, ring, "assets", id=50, user_id=other, name="Other cash", kind="currency",
                       category="Cash", interest_basis="", profile="safe", icon="", units="", wrapper="",
                       created_at=datetime(2026, 1, 1))
        _insert_sealed(c, ring, "positions", id=50, user_id=other, asset_id=50, amount=5, currency="PLN",
                       value_in_base=5, price_used=1, base_currency="PLN", notes="",
                       timestamp=datetime(2026, 1, 1))
    before = _counts(eng)
    pre = _catalog(eng)
    assert pre["policies"] == [] and pre["functions"] == []

    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "composite ownership keys" in result.stdout
    assert _counts(eng) == before  # nothing lost, nothing moved
    migrated = _catalog(eng)

    fresh_url, cleanup = _fresh_pg()
    try:
        assert _run_schema(fresh_url).returncode == 0
        fresh = create_engine(fresh_url)
        assert migrated == _catalog(fresh)
        assert _fingerprint(eng) == _fingerprint(fresh)
        fresh.dispose()
    finally:
        cleanup()

    again = _run_schema(url, **AUTH_ENV)
    assert again.returncode == 0
    assert _catalog(eng) == migrated and _counts(eng) == before
    # The new key is live: the second user still owns their position, and cannot
    # be pointed at the first user's asset.
    with eng.connect() as c:
        assert c.execute(text("SELECT user_id FROM positions WHERE id = 50")).scalar() == other
    with pytest.raises(Exception, match="fk_positions_user_asset"):
        with eng.begin() as c:
            c.execute(text("UPDATE positions SET asset_id = 1 WHERE id = 50"))
    eng.dispose()


def test_rows_that_cross_users_stop_the_upgrade_before_anything_changes(legacy_db):
    url, dialect = legacy_db
    _pg_only(dialect)
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    _as_phase_one(eng)
    with eng.begin() as c:
        other = uuid.uuid4()
        c.execute(text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, now())"),
                  {"i": other, "h": "8" * 64})
        # A position of the second user that points at the first user's asset.
        from src.crypto.core import KeyRing, new_dek

        _insert_sealed(c, KeyRing(other, new_dek()), "positions", id=60, user_id=other, asset_id=1,
                       amount=5, currency="PLN", value_in_base=5, price_used=1, base_currency="PLN",
                       notes="", timestamp=datetime(2026, 1, 1))
    pre = _catalog(eng)
    result = _run_schema(url, **AUTH_ENV)
    assert result.returncode == 1
    assert "positions" in result.stderr and "another user" in result.stderr
    assert _catalog(eng) == pre  # no constraint, no policy, no function was added
    eng.dispose()


def test_an_old_database_is_served_to_the_runtime_role_under_row_security(legacy_db):
    """End to end: the schema job as owner with MYFINANCE_APP_ROLE, then the
    runtime role's own connection to the migrated legacy data."""
    url, dialect = legacy_db
    _pg_only(dialect)
    if not RUNTIME_URL:
        pytest.skip("needs the runtime role (MYFINANCE_TEST_OWNER_DATABASE_URL)")
    from sqlalchemy.engine import make_url

    role = make_url(RUNTIME_URL).username
    result = _run_schema(url, MYFINANCE_APP_ROLE=role, **AUTH_ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"granted read/write on public to {role}" in result.stdout

    eng = create_engine(url)
    with eng.connect() as c:
        owner = c.execute(text("SELECT id FROM users")).scalar()
    eng.dispose()

    rt = create_engine(make_url(RUNTIME_URL).set(database=make_url(url).database))
    try:
        with Session(rt, info={"user_id": owner}) as mine:
            assert mine.execute(text("SELECT count(*) FROM positions")).scalar() == 3
            assert mine.execute(text("SELECT count(*) FROM settings")).scalar() == 3
            # The runtime role can see its own rows - and they are ciphertext.
            assert mine.execute(text("SELECT amount FROM positions ORDER BY id LIMIT 1")).scalar()[:1] == b"\x01"
        with Session(rt, info={"user_id": uuid.uuid4()}) as stranger:
            assert stranger.execute(text("SELECT count(*) FROM positions")).scalar() == 0
        with Session(rt) as nobody:
            assert nobody.execute(text("SELECT count(*) FROM positions")).scalar() == 0
        with rt.connect() as raw:
            assert raw.execute(text("SELECT count(*) FROM assets")).scalar() == 0
    finally:
        rt.dispose()


def test_the_schema_job_refuses_a_runtime_role_that_would_bypass_row_security(legacy_db):
    url, dialect = legacy_db
    _pg_only(dialect)
    from sqlalchemy.engine import make_url

    owner_role = make_url(url).username
    result = _run_schema(url, MYFINANCE_APP_ROLE=owner_role, **AUTH_ENV)
    assert result.returncode == 1
    assert "would not be subject to row-level security" in result.stderr
