"""Encrypting the existing plaintext data in place (run by the schema job).

Before this release every value was stored as plain text, numbers and dates.
Now each is a ciphertext in a binary column (crypto/fields.py). This converts a
database that has the old shape:

* it works out, per table, which encrypted columns still have a plain type
  (a column that is already binary is done, so a second run finds nothing);
* every plaintext row must belong to the *bootstrap user* - the one person who
  used the single-user version. That user's key is derived exactly as their next
  sign-in will derive it (the KEK, their salt, and the secret in
  MYFINANCE_BOOTSTRAP_SUB, or MYFINANCE_BOOTSTRAP_KEY_SECRET when the key claim
  is not `sub`), created now if they have none yet. Plaintext rows of anyone
  else are not encrypted under a guess: the run stops and names them;
* the new column types are made and filled in one transaction, on both
  PostgreSQL (add a binary column, fill it, drop the old, rename) and SQLite
  (rebuild the table, as the ownership migration does), so a failure leaves the
  old, working schema and plaintext in place, and nothing is half converted.

The raw secret is used to derive the key and then dropped; it is not printed.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Column, LargeBinary, MetaData, Table, and_, bindparam, insert, inspect, select, text, update
from sqlalchemy import types as sqltypes
from sqlalchemy.engine import Connection, Engine

from .config import settings
from .crypto.core import (
    LOCAL_SECRET,
    DecryptionError,
    KeyRing,
    active_keks,
    new_dek,
    new_salt,
    unwrap_dek,
    wrap_dek,
)
from .crypto.fields import Encrypted, encrypted_columns
from .database import Base, engine

log = logging.getLogger(__name__)


class MigrationError(RuntimeError):
    """Raised for anything the operator has to fix; schema.py turns it into a SchemaError."""


def _is_binary(sa_type) -> bool:
    return isinstance(sa_type, sqltypes._Binary)


@dataclass
class TablePlan:
    table: Table
    legacy: list[str]  # encrypted columns whose database type is still a plain one
    present: set[str] = field(default_factory=set)  # every column that exists in the database table


def plan(eng: Engine | Connection) -> list[TablePlan]:
    insp = inspect(eng)
    plans = []
    for table in Base.metadata.sorted_tables:
        enc = encrypted_columns(table)
        if not enc or not insp.has_table(table.name):
            continue
        reflected = {c["name"]: c["type"] for c in insp.get_columns(table.name)}
        legacy = [c.name for c, _ in enc if c.name in reflected and not _is_binary(reflected[c.name])]
        if legacy:
            plans.append(TablePlan(table, legacy, set(reflected)))
    return plans


def legacy_view(plan_: TablePlan) -> Table:
    """The table as the database has it *now*: plain types where a column has
    not been converted, so old rows can be read with the types they were written
    with (Decimal, date, parsed JSON)."""
    cols = []
    for c in plan_.table.columns:
        if c.name not in plan_.present:
            continue
        if c.name in plan_.legacy:
            t = c.type.legacy_type()
        elif isinstance(c.type, Encrypted):
            t = LargeBinary()
        else:
            t = c.type
        cols.append(Column(c.name, t, primary_key=c.primary_key))
    return Table(plan_.table.name, MetaData(), *cols)


def plain_tables() -> dict[str, Table]:
    """Copies of every model table with the encrypted columns given back the
    plain type they replaced. The ownership migration (schema._migrate_sqlite)
    rebuilds old tables from these, not from the models: it copies plaintext
    rows across, and a binary column would happily (SQLite is not strict) store
    them as they are, after which the table would look already encrypted."""
    meta = MetaData()
    out = {}
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(meta)
        for col, etype in encrypted_columns(table):
            clone.c[col.name].type = etype.legacy_type()
        out[table.name] = clone
    return out


def raw_view(table: Table) -> Table:
    """The *new* table with its encrypted columns as plain binary, so a
    ciphertext is written as the bytes it is, not encrypted again."""
    cols = [
        Column(c.name, LargeBinary() if isinstance(c.type, Encrypted) else c.type, primary_key=c.primary_key)
        for c in table.columns
    ]
    return Table(table.name, MetaData(), *cols)


# --- Who owns the plaintext -----------------------------------------------------


def _rows_by_owner(conn: Connection, plans: list[TablePlan]) -> dict[str, dict[uuid.UUID, int]]:
    out: dict[str, dict[uuid.UUID, int]] = {}
    q = conn.dialect.identifier_preparer.quote
    for p in plans:
        name = p.table.name
        rows = conn.execute(text(f"SELECT user_id, count(*) FROM {q(name)} GROUP BY user_id")).all()
        owners = {}
        for user_id, n in rows:
            owners[user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))] = n
        if owners:
            out[name] = owners
    return out


def _bootstrap_secret() -> str:
    from . import auth

    if not settings.bootstrap_sub and not auth.auth_enabled():
        return LOCAL_SECRET
    if settings.key_claim == "sub":
        return settings.bootstrap_sub
    if not settings.bootstrap_key_secret:
        raise MigrationError(
            f"MYFINANCE_KEY_CLAIM is {settings.key_claim!r}, not `sub`: set "
            "MYFINANCE_BOOTSTRAP_KEY_SECRET to the bootstrap user's value of that claim, so their "
            "existing data can be encrypted under the key their next sign-in will derive"
        )
    return settings.bootstrap_key_secret


@dataclass
class Keys:
    rings: dict[uuid.UUID, KeyRing]
    # (user id, salt, wrapped, kek version) to write to `users`, for a user who had no key.
    new_key: tuple[uuid.UUID, bytes, bytes, int] | None = None


def resolve_keys(eng: Engine, plans: list[TablePlan]) -> Keys:
    """The key ring of the one user whose plaintext rows may be encrypted, or an
    error naming whatever is in the way. Reads only."""
    from . import schema

    with eng.connect() as conn:
        owners = _rows_by_owner(conn, plans)
        if not owners:
            return Keys({})  # empty tables: only their types change
        all_users = {u for per in owners.values() for u in per}
        boot_hash, _ = schema._bootstrap_identity()
        users = Base.metadata.tables["users"]
        row = conn.execute(
            select(users.c.id, users.c.key_salt, users.c.wrapped_dek, users.c.kek_version).where(
                users.c.subject_hash == boot_hash
            )
        ).first()
    if row is None:
        raise MigrationError(
            "there are plaintext rows to encrypt but no user matches the bootstrap identity "
            "(MYFINANCE_BOOTSTRAP_SUB / _ISS and the pepper): nothing can be encrypted for them"
        )
    boot_id = row[0] if isinstance(row[0], uuid.UUID) else uuid.UUID(str(row[0]))
    strangers = all_users - {boot_id}
    if strangers:
        detail = "; ".join(
            f"user {u}: "
            + ", ".join(f"{t}={per[u]}" for t, per in sorted(owners.items()) if u in per)
            for u in sorted(strangers, key=str)
        )
        raise MigrationError(
            "plaintext rows belong to user(s) other than the bootstrap user, and no key can be "
            f"derived for them here, so nothing was changed: {detail}. Assign or delete those rows "
            "(they should not exist) and run again."
        )
    keks = active_keks()
    secret = _bootstrap_secret()
    if not secret:
        raise MigrationError("the bootstrap user's key secret is empty (MYFINANCE_BOOTSTRAP_SUB)")
    salt, wrapped, version = row[1], row[2], row[3]
    if wrapped is None:
        salt, dek = new_salt(), new_dek()
        wrapped = wrap_dek(
            dek, user_id=boot_id, kek=keks.current_key, kek_version=keks.current, salt=salt, secret=secret
        )
        return Keys({boot_id: KeyRing(boot_id, dek)}, (boot_id, salt, wrapped, keks.current))
    try:
        dek = unwrap_dek(
            wrapped, user_id=boot_id, kek=keks.get(version), kek_version=version, salt=salt, secret=secret
        )
    except DecryptionError:
        raise MigrationError(
            "the bootstrap user already has a data key and it does not open with the configured "
            "KEK and MYFINANCE_BOOTSTRAP_SUB (or _KEY_SECRET): wrong value, or wrong KEK. "
            "Nothing was changed."
        ) from None
    return Keys({boot_id: KeyRing(boot_id, dek)})


# --- Converting ----------------------------------------------------------------


def _backfill(table_name: str, col: str, value, row):
    """Values the old single-user schema left blank that the application now
    expects filled in. Today: an asset's risk profile (it used to be derived at
    read time, then backfilled by a separate job step)."""
    if table_name == "assets" and col == "profile" and not value:
        from .profiles import for_category

        return for_category(row.get("category") or "")
    return value


def _convert_rows(p: TablePlan, rows: list[dict], keys: Keys) -> list[dict]:
    out = []
    for row in rows:
        user_id = row["user_id"]
        user_id = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))
        ring = keys.rings[user_id]  # resolve_keys guarantees every owner has one
        new = dict(row)
        for col in p.legacy:
            etype = p.table.columns[col].type
            value = _backfill(p.table.name, col, row[col], row)
            new[col] = etype.seal_with(ring, value)
        out.append(new)
    return out


def _run_postgresql(eng: Engine, plans: list[TablePlan], keys: Keys) -> None:
    q = eng.dialect.identifier_preparer.quote
    with eng.begin() as conn:
        _store_new_key(conn, keys)
        for p in plans:
            n = q(p.table.name)
            view = legacy_view(p)
            rows = [dict(r) for r in conn.execute(select(view)).mappings()]
            converted = _convert_rows(p, rows, keys)
            for col in p.legacy:
                conn.execute(text(f"ALTER TABLE {n} ADD COLUMN {q(col + '__enc')} BYTEA"))
            pk = [c for c in p.table.primary_key.columns]
            if converted:
                holder = Table(
                    p.table.name,
                    MetaData(),
                    *[Column(c.name, c.type, primary_key=True) for c in pk],
                    *[Column(col + "__enc", LargeBinary()) for col in p.legacy],
                )
                stmt = (
                    update(holder)
                    .where(and_(*[holder.c[c.name] == bindparam("pk_" + c.name) for c in pk]))
                    .values({col + "__enc": bindparam("v_" + col) for col in p.legacy})
                )
                conn.execute(
                    stmt,
                    [
                        {
                            **{"pk_" + c.name: r[c.name] for c in pk},
                            **{"v_" + col: r[col] for col in p.legacy},
                        }
                        for r in converted
                    ],
                )
            for col in p.legacy:
                # Dropping the column drops its indexes with it.
                conn.execute(text(f"ALTER TABLE {n} DROP COLUMN {q(col)}"))
                conn.execute(text(f"ALTER TABLE {n} RENAME COLUMN {q(col + '__enc')} TO {q(col)}"))
                if not p.table.columns[col].nullable:
                    conn.execute(text(f"ALTER TABLE {n} ALTER COLUMN {q(col)} SET NOT NULL"))
            log.info("encrypted %s: %s (%d row(s))", p.table.name, ", ".join(p.legacy), len(converted))


def _run_sqlite(eng: Engine, plans: list[TablePlan], keys: Keys) -> None:
    """Each table is rebuilt: its rows read with their old types, the table
    renamed aside, recreated from the model (binary columns), the sealed rows
    inserted, the old one dropped. `legacy_alter_table` keeps RENAME from
    rewriting other tables' foreign keys; an explicit BEGIN makes the whole
    thing one transaction (pysqlite would leave DDL outside one)."""
    raw = eng.raw_connection()
    try:
        raw.execute("PRAGMA legacy_alter_table=ON")
    finally:
        raw.close()
    try:
        with eng.begin() as conn:
            conn.exec_driver_sql("BEGIN")
            _store_new_key(conn, keys)
            for p in plans:
                t = p.table
                aside = f"{t.name}__plain"
                rows = [dict(r) for r in conn.execute(select(legacy_view(p))).mappings()]
                converted = _convert_rows(p, rows, keys)
                conn.exec_driver_sql(f'ALTER TABLE "{t.name}" RENAME TO "{aside}"')
                stale = conn.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = ? "
                    "AND sql IS NOT NULL",
                    (aside,),
                ).fetchall()
                for (name,) in stale:
                    conn.exec_driver_sql(f'DROP INDEX "{name}"')
                t.create(conn)
                if converted:
                    keep = {c.name for c in t.columns}
                    conn.execute(
                        insert(raw_view(t)),
                        [{k: v for k, v in r.items() if k in keep} for r in converted],
                    )
                conn.exec_driver_sql(f'DROP TABLE "{aside}"')
                log.info("encrypted %s: %s (%d row(s))", t.name, ", ".join(p.legacy), len(converted))
    finally:
        raw = eng.raw_connection()
        try:
            raw.execute("PRAGMA legacy_alter_table=OFF")
        finally:
            raw.close()


def _store_new_key(conn: Connection, keys: Keys) -> None:
    if keys.new_key is None:
        return
    user_id, salt, wrapped, version = keys.new_key
    users = Base.metadata.tables["users"]
    conn.execute(
        update(users)
        .where(users.c.id == user_id, users.c.wrapped_dek.is_(None))
        .values(key_salt=salt, wrapped_dek=wrapped, kek_version=version)
    )


def migrate_encryption(eng: Engine | None = None) -> list[str]:
    """Bring every encrypted column of an old database to its ciphertext type,
    encrypting the rows. Returns the names of the tables changed (empty when
    there was nothing to do - the second run of anything). Raises
    `MigrationError` before touching anything if it cannot proceed."""
    eng = eng or engine
    plans = plan(eng)
    if not plans:
        return []
    keys = resolve_keys(eng, plans)
    if eng.dialect.name == "sqlite":
        _run_sqlite(eng, plans, keys)
    else:
        _run_postgresql(eng, plans, keys)
    for ring in keys.rings.values():
        ring.destroy()
    return [p.table.name for p in plans]
