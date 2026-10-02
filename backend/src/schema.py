"""Schema creation, migration and seeding - run as the *owning* role.

The application's runtime role deliberately holds no DDL rights, so none of
this can happen when the API starts. A Helm hook Job runs `python -m
src.schema` with the owner's client certificate before the new backend rolls
out; the app then connects with a role that can only read and write rows.

Safe to run repeatedly: every step checks before it acts.

On PostgreSQL the job also installs row-level security (rls.py) and the
functions the application's role calls for the work that crosses users, and
adds the composite foreign keys that keep a child row inside its owner's data.

Per-user encryption (`migrate_encryption`, see encmigrate.py) is the last data
step: it needs `MYFINANCE_KEKS`, and `MYFINANCE_BOOTSTRAP_SUB` when there are
plaintext rows to encrypt. Before anything is written the job checks the
configured KEK against the key-check values already in the database (a wrong
Secret stops it here, by name), and the key-check value of every configured
version is recorded.

Multi-user ownership (`migrate_ownership`) is the one step that rewrites
existing tables. It runs on both databases the application supports - SQLite
(local development) and PostgreSQL - and in one transaction on each, so a
failure leaves the previous schema intact rather than half converted.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import Uuid, bindparam, insert, inspect, select, text
from sqlalchemy.engine import Connection, Engine

from . import auth, encmigrate, identity, rls
from .config import settings
from .crypto.core import KekError, KeyRing
from .database import Base, engine
from .models import (  # noqa: F401 (import registers the tables on Base)
    asset,
    contact,
    expense,
    income,
    insight,
    keycheck,
    monthly,
    position,
    report,
    settings as settings_model,
    user,
)
from .models.asset import Asset
from .models.user import Owned, User
from .scoping import open_session
from .services import keys as key_service


class SchemaError(RuntimeError):
    """The schema cannot be brought up to date without operator input."""


def migrate() -> None:
    """Add columns that create_all() cannot introduce on an existing table.

    create_all only creates missing *tables*, so a column added to a model
    after the database exists stays absent until it is added here. Kept small
    on purpose - past a handful of columns this wants a real migration tool.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    binary = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
    # (table, column, DDL to add it, optional index DDL)
    wanted = [
        ("assets", "category",
         "ALTER TABLE assets ADD COLUMN category VARCHAR(60) NOT NULL DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS ix_assets_category ON assets (category)"),
        ("assets", "interest_basis",
         "ALTER TABLE assets ADD COLUMN interest_basis VARCHAR(10) NOT NULL DEFAULT ''",
         None),
        ("positions", "accrues_from",
         "ALTER TABLE positions ADD COLUMN accrues_from DATE",
         None),
        ("assets", "profile",
         "ALTER TABLE assets ADD COLUMN profile VARCHAR(12) NOT NULL DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS ix_assets_profile ON assets (profile)"),
        ("positions", "flow_in_base",
         "ALTER TABLE positions ADD COLUMN flow_in_base NUMERIC(20,4)",
         None),
        ("assets", "wrapper",
         "ALTER TABLE assets ADD COLUMN wrapper VARCHAR(8) NOT NULL DEFAULT ''",
         None),
        ("income_entries", "units",
         "ALTER TABLE income_entries ADD COLUMN units NUMERIC(10,2)",
         None),
        ("insights", "data_localized",
         "ALTER TABLE insights ADD COLUMN data_localized JSON",
         None),
        ("monthly_records", "commitments_paid",
         "ALTER TABLE monthly_records ADD COLUMN commitments_paid TEXT",
         None),
        ("monthly_records", "other_spent",
         "ALTER TABLE monthly_records ADD COLUMN other_spent NUMERIC(20,2)",
         None),
        ("assets", "archived_at",
         "ALTER TABLE assets ADD COLUMN archived_at TIMESTAMP",
         None),
        # --- per-user encryption: key material, recovery code, birth year ---
        ("users", "key_salt", f"ALTER TABLE users ADD COLUMN key_salt {binary}", None),
        ("users", "wrapped_dek", f"ALTER TABLE users ADD COLUMN wrapped_dek {binary}", None),
        ("users", "kek_version", "ALTER TABLE users ADD COLUMN kek_version INTEGER", None),
        ("users", "recovery_id",
         "ALTER TABLE users ADD COLUMN recovery_id VARCHAR(32)",
         "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_recovery_id ON users (recovery_id)"),
        ("users", "recovery_salt", f"ALTER TABLE users ADD COLUMN recovery_salt {binary}", None),
        ("users", "recovery_kdf", "ALTER TABLE users ADD COLUMN recovery_kdf VARCHAR(64)", None),
        ("users", "recovery_wrapped_dek",
         f"ALTER TABLE users ADD COLUMN recovery_wrapped_dek {binary}", None),
        ("users", "recovery_verifier", f"ALTER TABLE users ADD COLUMN recovery_verifier {binary}", None),
        ("users", "recovery_created_at", "ALTER TABLE users ADD COLUMN recovery_created_at TIMESTAMP", None),
        ("users", "recovery_confirmed_at",
         "ALTER TABLE users ADD COLUMN recovery_confirmed_at TIMESTAMP", None),
        ("users", "recovery_failures",
         "ALTER TABLE users ADD COLUMN recovery_failures INTEGER NOT NULL DEFAULT 0", None),
        ("users", "recovery_locked_until",
         "ALTER TABLE users ADD COLUMN recovery_locked_until TIMESTAMP", None),
        ("users", "birth_year", f"ALTER TABLE users ADD COLUMN birth_year {binary}", None),
        ("reports", "status_note",
         "ALTER TABLE reports ADD COLUMN status_note VARCHAR(24) NOT NULL DEFAULT ''", None),
        ("insights", "status_note",
         "ALTER TABLE insights ADD COLUMN status_note VARCHAR(24) NOT NULL DEFAULT ''", None),
    ]
    for table, column, add_sql, index_sql in wanted:
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(add_sql))
            if index_sql:
                conn.execute(text(index_sql))
        print(f"  + {table}.{column}")


# --- Ownership ------------------------------------------------------------


def owned_tables() -> list:
    """Every table whose rows belong to a user, derived from the models so a
    table added later with the `Owned` mixin is picked up without editing this
    list."""
    return [m.class_.__table__ for m in Base.registry.mappers if issubclass(m.class_, Owned)]


def _bootstrap_identity() -> tuple[str, uuid.UUID | None]:
    """(subject hash, fixed user id or None) of whoever inherits existing data.

    The operator names the person: the `sub` their tokens carry
    (MYFINANCE_BOOTSTRAP_SUB) and, if that is not the configured issuer, the
    `iss` (MYFINANCE_BOOTSTRAP_ISS). Both are hashed with the pepper exactly as
    a login hashes them, so that person's next sign-in resolves to this user and
    finds their data. The raw values are not stored or printed by this.

    With none given and authentication off there is exactly one possible user -
    the fixed local one the running application will use - so the data goes to
    them. With none given and authentication on, there is no safe guess, and
    the run stops.
    """
    sub = settings.bootstrap_sub
    if not sub:
        if not auth.auth_enabled():
            print(
                "  ! authentication is not configured here: existing data goes to the "
                "local development user. If the application runs with authentication, "
                "this job is missing its MYFINANCE_AUTH_* / MYFINANCE_BOOTSTRAP_* settings."
            )
            return identity.local_subject_hash(), identity.LOCAL_USER_ID
        raise SchemaError(
            "existing data has no owner and authentication is enabled: set "
            "MYFINANCE_BOOTSTRAP_SUB (the `sub` claim of the person who owns it) "
            "and, if that is not the configured issuer, MYFINANCE_BOOTSTRAP_ISS"
        )
    iss = settings.bootstrap_iss or auth.issuer()
    if not iss:
        raise SchemaError("MYFINANCE_BOOTSTRAP_SUB is set but there is no issuer: set MYFINANCE_BOOTSTRAP_ISS")
    try:
        return identity.subject_hash(iss, sub), None
    except identity.PepperMissing as exc:
        raise SchemaError(str(exc)) from exc


def _has_rows(conn: Connection, table_name: str) -> bool:
    quoted = conn.dialect.identifier_preparer.quote(table_name)
    return conn.execute(text(f"SELECT 1 FROM {quoted} LIMIT 1")).first() is not None


def _ensure_user(conn: Connection, subject_hash: str, fixed_id: uuid.UUID | None) -> uuid.UUID:
    users = User.__table__
    found = conn.execute(
        select(users.c.id).where(users.c.subject_hash == subject_hash)
    ).scalar_one_or_none()
    if found is not None:
        return found
    new_id = fixed_id or uuid.uuid4()
    conn.execute(
        insert(users).values(
            id=new_id,
            subject_hash=subject_hash,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    print("  + created the user that inherits existing data")
    return new_id


def _owner_param(owner: uuid.UUID):
    return bindparam("owner", value=owner, type_=Uuid)


def migrate_ownership(eng: Engine | None = None) -> None:
    """Give every data table an owner, and assign existing rows to one user.

    Tables created fresh by create_all() already have `user_id`; this converts
    the ones that predate it. Per table: add `user_id UUID NOT NULL` with a
    foreign key to `users` and an index, make unique constraints per user, and
    for `settings` make the primary key (user_id, key). Existing rows - which
    all belong to the one person who used the single-user version - go to the
    bootstrap user (see _bootstrap_identity), created here if it is not there.

    Idempotent: a table that already has `user_id` is left alone, so a second
    run finds nothing to do. `users` itself is made by create_all() beforehand.
    """
    eng = eng or engine
    insp = inspect(eng)
    legacy = [
        t for t in owned_tables()
        if insp.has_table(t.name)
        and "user_id" not in {c["name"] for c in insp.get_columns(t.name)}
    ]
    if not legacy:
        return
    with eng.connect() as probe:
        needs_owner = any(_has_rows(probe, t.name) for t in legacy)
    # Resolved before anything is touched, so a missing setting fails the run
    # cleanly instead of after some tables have been rewritten.
    boot = _bootstrap_identity() if needs_owner else None

    if eng.dialect.name == "sqlite":
        _migrate_sqlite(eng, legacy, boot)
    else:
        _migrate_postgresql(eng, legacy, boot)
    print(f"  + ownership: {', '.join(t.name for t in legacy)}")


def _migrate_postgresql(eng: Engine, legacy: list, boot) -> None:
    q = eng.dialect.identifier_preparer.quote
    with eng.begin() as conn:
        owner = _ensure_user(conn, *boot) if boot else None
        insp = inspect(conn)
        for t in legacy:
            n = q(t.name)
            conn.execute(text(f"ALTER TABLE {n} ADD COLUMN user_id UUID"))
            if owner is not None:
                conn.execute(
                    text(f"UPDATE {n} SET user_id = :owner WHERE user_id IS NULL")
                    .bindparams(_owner_param(owner))
                )
            conn.execute(text(f"ALTER TABLE {n} ALTER COLUMN user_id SET NOT NULL"))
            conn.execute(text(
                f"ALTER TABLE {n} ADD CONSTRAINT {q(t.name + '_user_id_fkey')} "
                f"FOREIGN KEY (user_id) REFERENCES users (id)"
            ))
            if t.name != "settings":
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS {q('ix_' + t.name + '_user_id')} ON {n} (user_id)"
                ))

            if t.name == "monthly_records":
                # Was a unique index on `month` alone: one record per month for
                # the whole database. Now one per user per month.
                conn.execute(text("DROP INDEX IF EXISTS ix_monthly_records_month"))
                conn.execute(text(
                    "ALTER TABLE monthly_records ADD CONSTRAINT uq_monthly_user_month "
                    "UNIQUE (user_id, month)"
                ))
            elif t.name == "income_entries":
                conn.execute(text(
                    "ALTER TABLE income_entries DROP CONSTRAINT IF EXISTS uq_income_entry_source_month"
                ))
                conn.execute(text(
                    "ALTER TABLE income_entries ADD CONSTRAINT uq_income_entry_user_source_month "
                    "UNIQUE (user_id, source_id, month)"
                ))
            elif t.name == "settings":
                pk = insp.get_pk_constraint("settings").get("name") or "settings_pkey"
                conn.execute(text(f"ALTER TABLE settings DROP CONSTRAINT {q(pk)}"))
                conn.execute(text(
                    f"ALTER TABLE settings ADD CONSTRAINT {q(pk)} PRIMARY KEY (user_id, key)"
                ))


def _migrate_sqlite(eng: Engine, legacy: list, boot) -> None:
    """SQLite cannot add a NOT NULL column without a default, nor add a foreign
    key or change a primary key on an existing table, so each legacy table is
    rebuilt: renamed aside, recreated from the model, copied across with the
    owner filled in, and dropped.

    `legacy_alter_table` keeps RENAME from also rewriting other tables' foreign
    keys to point at the table being moved aside. An explicit BEGIN makes the
    whole rebuild one transaction - pysqlite would otherwise leave DDL outside
    one - so an error rolls back to the old schema untouched.
    """
    raw = eng.raw_connection()
    try:
        raw.execute("PRAGMA legacy_alter_table=ON")
    finally:
        raw.close()
    try:
        with eng.begin() as conn:
            conn.exec_driver_sql("BEGIN")
            owner = _ensure_user(conn, *boot) if boot else None
            for t in legacy:
                aside = f"{t.name}__premulti"
                old_cols = {c["name"] for c in inspect(conn).get_columns(t.name)}
                conn.exec_driver_sql(f'ALTER TABLE "{t.name}" RENAME TO "{aside}"')
                # Index names are global in SQLite and the recreated table wants
                # the same ones.
                stale = conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
                    "AND sql IS NOT NULL",
                    (aside,),
                ).fetchall()
                for (name,) in stale:
                    conn.exec_driver_sql(f'DROP INDEX "{name}"')
                # Rebuilt with the *plain* types the data has now (see
                # encmigrate.plain_tables): encryption is a later step.
                encmigrate.plain_tables()[t.name].create(conn)
                cols = [c.name for c in t.columns if c.name != "user_id" and c.name in old_cols]
                col_list = ", ".join(f'"{c}"' for c in cols)
                if owner is not None:
                    conn.execute(
                        text(
                            f'INSERT INTO "{t.name}" ({col_list}, user_id) '
                            f'SELECT {col_list}, :owner FROM "{aside}"'
                        ).bindparams(_owner_param(owner))
                    )
                conn.exec_driver_sql(f'DROP TABLE "{aside}"')
    finally:
        raw = eng.raw_connection()
        try:
            raw.execute("PRAGMA legacy_alter_table=OFF")
        finally:
            raw.close()


# Parent -> child links that must stay inside one user: (child table, child
# column, parent table, unique constraint on the parent, composite FK name).
# The models declare the same constraints (so a fresh database gets them from
# create_all); this brings an existing PostgreSQL database up to the same shape.
OWNED_LINKS = [
    ("positions", "asset_id", "assets", "uq_assets_user_id_id", "fk_positions_user_asset"),
    ("income_entries", "source_id", "income_sources", "uq_income_sources_user_id_id",
     "fk_income_entries_user_source"),
]


def _has_constraint(conn: Connection, table: str, name: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(:t) AND conname = :n"),
        {"t": f"public.{table}", "n": name},
    ).first() is not None


def migrate_integrity(eng: Engine | None = None) -> None:
    """Make the database itself refuse a child row that points at another
    user's parent: `(user_id, asset_id)` on positions -> assets and
    `(user_id, source_id)` on income_entries -> income_sources.

    Row-level security cannot do this: foreign-key checks run with it bypassed,
    so a plain `asset_id` reference accepts any user's asset (and its error
    message tells you the id exists). Each link gets a unique constraint on the
    parent's (user_id, id) to point at, the composite foreign key, and loses the
    single-column foreign key it makes redundant.

    PostgreSQL only, and idempotent: each step checks what is already there.
    SQLite does not enforce foreign keys unless asked to and cannot add one to
    an existing table without rebuilding it, so an existing SQLite database
    keeps its old (decorative) single-column keys; a new one gets the composite
    ones from create_all, and the ownership rebuild above recreates the legacy
    tables from the models.

    Rows that already cross users would make the new key fail. That cannot
    happen through the application, but it is checked first so the failure
    names the table instead of being a bare constraint error - and the run
    stops rather than guessing which user the row belongs to.
    """
    eng = eng or engine
    if eng.dialect.name != "postgresql":
        return
    q = eng.dialect.identifier_preparer.quote
    done = []
    with eng.begin() as conn:
        for child, column, parent, unique, fk in OWNED_LINKS:
            if not (inspect(conn).has_table(child) and inspect(conn).has_table(parent)):
                continue
            if _has_constraint(conn, child, fk):
                continue
            crossing = conn.execute(text(
                f"SELECT count(*) FROM {q(child)} c JOIN {q(parent)} p ON p.id = c.{q(column)} "
                f"WHERE p.user_id <> c.user_id"
            )).scalar_one()
            if crossing:
                raise SchemaError(
                    f"{crossing} row(s) in {child} point at a {parent} row owned by another "
                    f"user; fix or delete them before the {fk} constraint can be added"
                )
            if not _has_constraint(conn, parent, unique):
                conn.execute(text(
                    f"ALTER TABLE {q(parent)} ADD CONSTRAINT {q(unique)} UNIQUE (user_id, id)"
                ))
            conn.execute(text(
                f"ALTER TABLE {q(child)} ADD CONSTRAINT {q(fk)} "
                f"FOREIGN KEY (user_id, {q(column)}) REFERENCES {q(parent)} (user_id, id)"
            ))
            for old in inspect(conn).get_foreign_keys(child):
                if old["constrained_columns"] == [column] and old["name"]:
                    conn.execute(text(f"ALTER TABLE {q(child)} DROP CONSTRAINT {q(old['name'])}"))
            done.append(fk)
    if done:
        print(f"  + composite ownership keys: {', '.join(done)}")


def secure_postgresql(eng: Engine | None = None) -> None:
    """Row-level security and its functions (see rls.py), in one transaction.

    Must run as the role that owns the tables - the schema job - and is
    idempotent: policies are dropped and recreated, functions replaced.
    """
    eng = eng or engine
    if eng.dialect.name != "postgresql":
        return
    try:
        with eng.begin() as conn:
            rls.apply(conn, [t.name for t in owned_tables()])
    except rls.RowSecurityError as exc:
        raise SchemaError(str(exc)) from exc
    print("  + row-level security (forced) on the owned tables and users")


def move_terms_to_users() -> None:
    """Terms acceptance used to be a per-database setting; it is now a column
    on the user. Carry any old `terms_accepted` setting over to the user that
    owns it and delete it, so a person who already accepted is not asked again.

    Only possible while `settings.value` is still plaintext: it runs before the
    encryption migration, which is also the only time such a row can exist (the
    move has been part of every schema run since the column was added, so a
    database that has been through one has none left). Once the column is
    encrypted there is nothing to move and no key to read it with.
    """
    from sqlalchemy import delete

    insp = inspect(engine)
    if not insp.has_table("settings"):
        return
    value_type = {c["name"]: c["type"] for c in insp.get_columns("settings")}.get("value")
    if value_type is None or encmigrate._is_binary(value_type):
        return
    settings_t = Base.metadata.tables["settings"]
    users_t = User.__table__
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT user_id, value FROM settings WHERE key = 'terms_accepted'")
        ).all()
        for user_id, value in rows:
            user_id = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
            owner = conn.execute(
                select(users_t.c.id, users_t.c.terms_version).where(users_t.c.id == user_id)
            ).first()
            if owner is not None and owner[1] is None and value:
                data = json.loads(value)
                accepted_at = data.get("accepted_at")
                parsed = None
                if accepted_at:
                    parsed = datetime.fromisoformat(accepted_at)
                    if parsed.tzinfo is not None:
                        # Naive UTC, like every other timestamp column.
                        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                conn.execute(
                    users_t.update()
                    .where(users_t.c.id == user_id)
                    .values(terms_version=data.get("version"), terms_accepted_at=parsed)
                )
        if rows:
            conn.execute(delete(settings_t).where(settings_t.c.key == "terms_accepted"))
    if rows:
        print(f"  + moved terms acceptance to {len(rows)} user(s)")


# --- Data ---------------------------------------------------------------


def backfill_profiles(db) -> None:
    """Give every unclassified asset the band its class implies.

    Takes a keyed session (an asset's class and band are encrypted, so this has
    to read them as the owner) and only touches rows that have no profile yet,
    so a deliberate per-asset override is never overwritten by a later run.
    Existing databases get this done while their rows are encrypted
    (encmigrate); this is for what the demo seeder and tests create.
    """
    from .profiles import for_category

    rows = [a for a in db.query(Asset).all() if not a.profile]
    for a in rows:
        a.profile = for_category(a.category)
    if rows:
        db.commit()
        print(f"  + classified {len(rows)} asset(s) by risk profile")


def seed_features(user_id: uuid.UUID, keyring: KeyRing | None = None) -> None:
    """Decide one user's advanced-feature defaults, once.

    Only the demo seeder needs this now: a new user has no `features` row,
    which already means "everything off" (routes/helpers.get_features), and an
    existing database keeps the row it was given when it was single-user.

    Everything on when the user already holds positions, income sources, saved
    FIRE settings or a report - they predate the feature and must not lose
    anything - otherwise everything off. Only ever runs when the `features` key
    is absent, so a person's own later choice is never overwritten.
    """
    from .models.income import IncomeSource
    from .models.position import Position
    from .models.report import Report
    from .models.settings import Setting

    if keyring is None and user_id == identity.LOCAL_USER_ID:
        from .services.users import local_account

        keyring = local_account(provision=False).keyring
    db = open_session(user_id, keyring)
    try:
        if db.query(Setting).filter(Setting.key == "features").first():
            return
        has_existing_data = (
            db.query(Position.id).first() is not None
            or db.query(IncomeSource.id).first() is not None
            or db.query(Setting).filter(Setting.key == "fire").first() is not None
            or db.query(Report.id).first() is not None
        )
        value = {
            "portfolio": has_existing_data,
            "fire": has_existing_data,
            "tax": has_existing_data,
            "insights": has_existing_data,
        }
        db.add(Setting(key="features", value=json.dumps(value)))
        db.commit()
        if has_existing_data:
            print("  + existing data found: advanced features start on")
        else:
            print("  + new database: advanced features start off")
    finally:
        db.close()


def grant_runtime_role(role: str, eng: Engine | None = None) -> None:
    """Give the application role exactly what it needs and nothing more.

    Rows it may read and write; tables and schemas it may not create, drop or
    alter. Sequences are needed because the primary keys are generated. On
    `users` it may read (its own row, by policy) and update only the columns
    listed below - terms acceptance, its own key material and recovery code, its
    birth year: accounts are added through a function, never inserted or deleted
    by the role. `key_check` it may only read.

    Refuses a role that would ignore row-level security - a superuser, one with
    BYPASSRLS, or one that is (a member of) the owner - because granting it
    rights would then hand over every user's rows.
    """
    if not role:
        return
    eng = eng or engine
    database = eng.url.database
    q = eng.dialect.identifier_preparer.quote
    with eng.begin() as conn:
        attrs = conn.execute(
            text(
                "SELECT r.rolsuper, r.rolbypassrls, pg_has_role(r.oid, current_user, 'MEMBER') "
                "FROM pg_roles r WHERE r.rolname = :r"
            ),
            {"r": role},
        ).first()
        if attrs is None:
            raise SchemaError(f"runtime role {role!r} does not exist")
        if attrs[0] or attrs[1] or attrs[2]:
            raise SchemaError(
                f"runtime role {role!r} would not be subject to row-level security "
                f"(superuser={attrs[0]}, bypassrls={attrs[1]}, member of the owner={attrs[2]})"
            )
        statements = [
            f"GRANT CONNECT ON DATABASE {q(database)} TO {q(role)}",
            f"GRANT USAGE ON SCHEMA public TO {q(role)}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {q(role)}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {q(role)}",
            # Anything this Job creates in future runs is covered without re-granting.
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {q(role)}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {q(role)}",
            # users: narrower than every other table.
            f"REVOKE ALL ON TABLE users FROM {q(role)}",
            f"GRANT SELECT ON TABLE users TO {q(role)}",
            # Its own key material, recovery code, throttle and birth year: the
            # columns a signed-in user's own requests keep up to date (RLS limits
            # these updates to the caller's row).
            f"GRANT UPDATE (terms_version, terms_accepted_at, key_salt, wrapped_dek, kek_version, "
            f"recovery_id, recovery_salt, recovery_kdf, recovery_wrapped_dek, recovery_verifier, "
            f"recovery_created_at, recovery_confirmed_at, recovery_failures, recovery_locked_until, "
            f"birth_year) ON TABLE users TO {q(role)}",
            # Key-check values are written by this job only.
            f"REVOKE ALL ON TABLE key_check FROM {q(role)}",
            f"GRANT SELECT ON TABLE key_check TO {q(role)}",
        ]
        for sql in statements:
            conn.execute(text(sql))
        if conn.execute(text("SELECT to_regprocedure(:f)"), {"f": rls.function_signatures()[0]}).scalar():
            rls.grant_functions(conn, role)
    print(f"  + granted read/write on public to {role}")


def verify_kek() -> None:
    """Refuse to go on if the configured KEK is not the one this database was
    initialised with. Read-only: runs before anything is written."""
    keks = key_service.active_keks()
    if not inspect(engine).has_table("key_check"):
        return
    with engine.connect() as conn:
        problems = key_service.mismatches(keks, key_service._stored(conn))
    if problems:
        raise KekError("; ".join(problems))


def record_key_checks() -> None:
    with engine.begin() as conn:
        added = key_service.ensure_key_check(conn)
    if added:
        print(f"  + key-check value(s) for KEK version(s) {', '.join(str(v) for v in added)}")


def main() -> int:
    print(f"schema: {engine.url.drivername} -> {engine.url.database}")
    try:
        auth.validate_config(schema_job=True)
        keks = key_service.active_keks()
        if keks.development:
            print(
                "  ! no MYFINANCE_KEKS: using the public development KEK. Fine for a local "
                "database, never for a real one."
            )
        # Is this the KEK the database was initialised with? First of all, before
        # anything - even DDL - is written under a Secret that may be wrong.
        verify_kek()
        # Brand-new tables (including `users`) come out of create_all with
        # ownership built in; tables that already exist are converted below.
        Base.metadata.create_all(bind=engine)
        migrate()
        record_key_checks()
        migrate_ownership()
        migrate_integrity()
        move_terms_to_users()
        done = encmigrate.migrate_encryption()
        if done:
            print(f"  + encrypted: {', '.join(done)}")
        secure_postgresql()
        if engine.dialect.name == "postgresql":
            grant_runtime_role(os.environ.get("MYFINANCE_APP_ROLE", ""))
    except (SchemaError, auth.AuthConfigError, KekError, encmigrate.MigrationError) as exc:
        print(f"schema: {exc}", file=sys.stderr)
        return 1
    print("schema: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
