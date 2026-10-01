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
    MYFINANCE_AUTH_REQUIRE_AT_JWT_TYP="true",
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
                         MYFINANCE_AUTH_REQUIRE_AT_JWT_TYP="true", MYFINANCE_SUBJECT_PEPPER=PEPPER)
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
        for t in OWNED + ["users"]:
            c.execute(text(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY'))
            c.execute(text(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY'))
        for (name, table) in c.execute(text("SELECT policyname, tablename FROM pg_policies")).all():
            c.execute(text(f'DROP POLICY "{name}" ON "{table}"'))
        c.execute(text("DROP FUNCTION public.myfinance_get_or_create_user(text, uuid)"))
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
    assert {p[0] for p in cat["policies"]} == set(OWNED) | {"users"}
    assert all(f[1] and f[2] for f in cat["flags"] if f[0] in OWNED + ["users"])
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
        c.execute(text(
            "INSERT INTO assets (id, user_id, name, kind, category, interest_basis, profile, icon, units, wrapper, created_at) "
            "VALUES (50, :u, 'Other cash', 'currency', 'Cash', '', 'safe', '', '', '', now())"), {"u": other})
        c.execute(text(
            "INSERT INTO positions (id, user_id, asset_id, amount, currency, value_in_base, price_used, base_currency, notes, timestamp) "
            "VALUES (50, :u, 50, 5, 'PLN', 5, 1, 'PLN', '', now())"), {"u": other})
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
        c.execute(text(
            "INSERT INTO positions (id, user_id, asset_id, amount, currency, value_in_base, price_used, base_currency, notes, timestamp) "
            "VALUES (60, :u, 1, 5, 'PLN', 5, 1, 'PLN', '', now())"), {"u": other})
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
