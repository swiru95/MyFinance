"""The ownership migration (src/schema.py): an existing single-user database
is converted in place and every row ends up owned by the bootstrap user.

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
from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from src import identity

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
    MYFINANCE_SUBJECT_PEPPER=PEPPER,
    MYFINANCE_BOOTSTRAP_SUB=BOOT_SUB,
)


def _counts(eng) -> dict[str, int]:
    with eng.connect() as c:
        return {n: c.execute(text(f'SELECT count(*) FROM "{n}"')).scalar() for n in OWNED}


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

    # ... and the data came across intact.
    meta = MetaData()
    pos = Table("positions", meta, autoload_with=eng)
    with eng.connect() as c:
        rows = c.execute(select(pos.c.id, pos.c.asset_id, pos.c.amount, pos.c.flow_in_base).order_by(pos.c.id)).all()
    assert [(r.id, r.asset_id, float(r.amount)) for r in rows] == [(1, 1, 1000.0), (2, 1, 1500.0), (3, 2, 10.0)]
    assert float(rows[1].flow_in_base) == 500.0
    with eng.connect() as c:
        assert c.execute(text("SELECT value FROM settings WHERE key = 'base_currency'")).scalar() == "EUR"
        assert c.execute(text("SELECT count(*) FROM settings WHERE key = 'terms_accepted'")).scalar() == 0
        assert c.execute(text("SELECT terms_accepted_at FROM users")).scalar() is not None
    eng.dispose()


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

    # The old indexes survived the rebuild (SQLite recreates every table).
    asset_indexes = {i["name"] for i in insp.get_indexes("assets")}
    assert {"ix_assets_category", "ix_assets_profile", "ix_assets_user_id"} <= asset_indexes

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
        ins = text(
            "INSERT INTO monthly_records (id, user_id, month, income, actual_spent, currency, notes, updated_at) "
            "VALUES (:id, :u, '2026-03', 1, 1, 'PLN', '', :t)"
        )
        conn.execute(ins.bindparams(id=100, u=other_param, t=datetime(2026, 1, 1)))
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with eng.begin() as conn:
            conn.execute(ins.bindparams(id=101, u=other_param, t=datetime(2026, 1, 1)))
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

    from src.models import Asset, Expense, Position, Setting
    from src.models.user import User

    eng = create_engine(url)
    with Session(eng) as plain:
        owner = plain.execute(select(User)).scalar_one()
    with Session(eng, info={"user_id": owner.id}) as mine:
        assert {a.name for a in mine.query(Asset).all()} == {"Cash", "Gold"}
        assert mine.query(func.count(Position.id)).scalar() == 3
        assert mine.query(Setting).filter(Setting.key == "base_currency").one().value == "EUR"
        assert mine.query(func.count(Expense.id)).scalar() == 2
    with Session(eng, info={"user_id": uuid.uuid4()}) as stranger:
        assert stranger.query(Asset).all() == []
        assert stranger.query(Setting).all() == []
    eng.dispose()


def test_a_second_run_changes_nothing(legacy_db):
    url, _ = legacy_db
    assert _run_schema(url, **AUTH_ENV).returncode == 0
    eng = create_engine(url)
    snapshot = _counts(eng)
    with eng.connect() as c:
        users_before = c.execute(text("SELECT id, subject_hash FROM users")).all()

    again = _run_schema(url, **AUTH_ENV)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "ownership" not in again.stdout
    assert _counts(eng) == snapshot
    with eng.connect() as c:
        assert c.execute(text("SELECT id, subject_hash FROM users")).all() == users_before
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
    eng = create_engine(url)
    with eng.connect() as c:
        assert c.execute(text("SELECT subject_hash FROM users")).scalar() == identity.local_subject_hash()
    eng.dispose()


def test_an_empty_legacy_database_is_converted_without_inventing_a_user(legacy_db):
    url, _ = legacy_db
    eng = create_engine(url)
    with eng.begin() as conn:
        for name in ("positions", "income_entries", "assets", "expenses", "income_sources",
                     "monthly_records", "insights", "reports", "settings"):
            conn.execute(text(f'DELETE FROM "{name}"'))
    # No data and no bootstrap settings: nothing to ask the operator.
    result = _run_schema(url, MYFINANCE_AUTH_ISSUER=ISSUER, MYFINANCE_AUTH_AUDIENCE=AUDIENCE,
                         MYFINANCE_SUBJECT_PEPPER=PEPPER)
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
    assert cols == {"id", "subject_hash", "created_at", "terms_version", "terms_accepted_at"}
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
