"""PostgreSQL row-level security (src/rls.py), tested the way an attacker - or a
bug - would meet it: connected as the application's *runtime* role, sending raw
SQL that goes round every filter the ORM adds.

Runs only against PostgreSQL with both roles configured:

    MYFINANCE_TEST_DATABASE_URL=postgresql+psycopg://<runtime role>@host/db
    MYFINANCE_TEST_OWNER_DATABASE_URL=postgresql+psycopg://<owner role>@host/db

(the owner makes the tables and may look across users; the runtime role is the
one the application uses). Elsewhere this module is skipped - SQLite has no
row-level security and the ORM scoping is covered by test_scoping.py.
"""
from __future__ import annotations

import threading
import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from src import encmigrate, rls, schema
from src.crypto.fields import Encrypted
from src.database import SessionLocal, engine
from src.models import (
    Asset, Expense, IncomeEntry, IncomeSource, Insight, MonthlyRecord, Position, Report, Setting, UserContact,
)
from src.scoping import open_system_session
from tests.conftest import _RINGS, TEST_OWNER_URL, make_user, owner_engine, session_for

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql" or not TEST_OWNER_URL,
    reason="needs PostgreSQL with MYFINANCE_TEST_OWNER_DATABASE_URL (runtime + owner roles)",
)

HASH_A, HASH_B = "a" * 64, "b" * 64
OWNED = [t.name for t in schema.owned_tables()]


# --- a database with two users' data ----------------------------------------------

def _populate(user_id: uuid.UUID, tag: str) -> None:
    with session_for(user_id) as s:
        asset = Asset(name=f"{tag}-asset", kind="currency")
        source = IncomeSource(name=f"{tag}-job", kind="uop", starts_on=date(2026, 1, 1))
        s.add_all([asset, source])
        s.flush()
        s.add_all([
            Position(asset_id=asset.id, amount=1, currency="PLN", value_in_base=1, price_used=1),
            IncomeEntry(source_id=source.id, month="2026-03", amount=100),
            Expense(name=f"{tag}-rent", amount=10, starts_on=date(2026, 1, 1)),
            MonthlyRecord(month="2026-03", income=1, actual_spent=1),
            Insight(kind="digest"),
            Report(),
            Setting(key="base_currency", value=tag),
            UserContact(notify_opt_in=False),
        ])
        s.commit()


def _raw(table: str):
    """The table as stored: encrypted columns plain binary, so a statement built
    from it carries ciphertext through untouched (no key needed, none applied)."""
    return encmigrate.raw_view(schema.Base.metadata.tables[table])


def _sealed(table: str, user: uuid.UUID, **values) -> dict:
    """A row's values with the encrypted ones sealed under `user`'s key, ready to
    insert through `_raw(table)` - what raw SQL from a compromised code path would
    have to send."""
    t = schema.Base.metadata.tables[table]
    ring = _RINGS[user]
    return {
        k: t.c[k].type.seal_with(ring, v) if isinstance(t.c[k].type, Encrypted) else v
        for k, v in values.items()
    }


@pytest.fixture
def two(db):
    """(alice, bob): two users, every owned table holding a row of each."""
    alice = make_user(HASH_A, provision=False)
    bob = make_user(HASH_B, provision=False)
    _populate(alice, "alice")
    _populate(bob, "bob")
    return alice, bob


def _ids_seen(user: uuid.UUID | None, table: str) -> set:
    """The user_ids behind every row of `table` that raw SQL can see when run in
    a session for `user` (None: a session with no user)."""
    s = session_for(user) if user else open_system_session()
    try:
        return {r[0] for r in s.execute(text(f'SELECT user_id FROM "{table}"'))}
    finally:
        s.close()


def isolation_problems(alice: uuid.UUID, bob: uuid.UUID) -> list[str]:
    """Everything wrong with how raw SQL sees the owned tables: another user's
    rows visible, or one's own rows not."""
    problems = []
    for t in OWNED:
        for me, other in ((alice, bob), (bob, alice)):
            seen = _ids_seen(me, t)
            if other in seen:
                problems.append(f"{t}: sees another user's rows")
            if me not in seen:
                problems.append(f"{t}: cannot see its own rows")
    return problems


def _owner(sql: str, **params):
    with owner_engine().begin() as conn:
        result = conn.execute(text(sql), params)
        return result.all() if result.returns_rows else []


# --- the role the application runs as ----------------------------------------------

def test_the_runtime_role_has_no_bypass_and_owns_nothing(two):
    with engine.connect() as conn:
        assert rls.runtime_role_problems(conn) == []
        sup, bypass = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        assert (sup, bypass) == (False, False)
        owners = conn.execute(
            text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public' AND tableowner = current_user")
        ).scalar_one()
        assert owners == 0
        # No DDL.
        with pytest.raises(ProgrammingError):
            conn.execute(text("CREATE TABLE stolen (id int)"))
        conn.rollback()
        with pytest.raises(ProgrammingError):
            conn.execute(text("ALTER TABLE assets DISABLE ROW LEVEL SECURITY"))


def test_the_application_refuses_to_run_as_the_owner(two):
    with pytest.raises(rls.RowSecurityError, match="not subject to row-level security"):
        rls.check_runtime_role(owner_engine())
    rls.check_runtime_role(engine)  # the runtime role is fine


def test_startup_fails_when_the_application_is_connected_as_the_owner(two, monkeypatch):
    from fastapi.testclient import TestClient

    from src.config import settings
    from src.main import app

    monkeypatch.setattr("src.main.engine", owner_engine())
    monkeypatch.setattr(settings, "rls_role_check", True)
    with pytest.raises(rls.RowSecurityError, match="MYFINANCE_RLS_ROLE_CHECK"):
        with TestClient(app):
            pass
    # The one-off override is honoured.
    monkeypatch.setattr(settings, "rls_role_check", False)
    with TestClient(app):
        pass


def test_row_security_is_enabled_and_forced_with_the_policies_in_place(two):
    rows = _owner(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'"
    )
    flags = {name: (on, forced) for name, on, forced in rows}
    for t in [*OWNED, "users"]:
        assert flags[t] == (True, True), t
    policies = {(r[0], r[1]) for r in _owner("SELECT tablename, policyname FROM pg_policies")}
    for t in OWNED:
        assert (t, rls.ISOLATION_POLICY) in policies, t
        assert (t, rls.OWNER_POLICY) in policies, t
    assert ("users", rls.USERS_SELECT_POLICY) in policies


# --- raw SQL sees only the current user's rows --------------------------------------

def test_raw_sql_sees_only_the_current_users_rows_in_every_table(two):
    alice, bob = two
    assert isolation_problems(alice, bob) == []


def test_raw_sql_cannot_reach_another_users_rows_by_id_or_by_join(two):
    alice, bob = two
    with session_for(alice) as s:
        bob_asset = _owner("SELECT id FROM assets WHERE user_id = :u", u=bob)[0][0]
        assert s.execute(text("SELECT count(*) FROM assets WHERE id = :i"), {"i": bob_asset}).scalar() == 0
        assert s.execute(
            text("SELECT count(*) FROM positions p JOIN assets a ON a.id = p.asset_id WHERE a.user_id = :u"),
            {"u": bob},
        ).scalar() == 0
        assert s.execute(
            text("SELECT count(*) FROM assets WHERE user_id IN (SELECT user_id FROM positions)")
        ).scalar() == 1


def test_a_query_with_no_variable_sees_nothing_and_does_not_error(two):
    with engine.connect() as conn:  # a raw connection: nothing ever set the variable
        for t in OWNED:
            assert conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() == 0, t
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 0


def test_an_empty_variable_sees_nothing_too(two):
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('myfinance.user_id', '', true)"))
        for t in OWNED:
            assert conn.execute(text(f'SELECT count(*) FROM "{t}"')).scalar() == 0, t


def test_the_orm_system_and_user_less_sessions_see_nothing_as_the_runtime_role(two):
    """open_system_session() lifts the ORM's filter, not the database's."""
    for t in OWNED:
        assert _ids_seen(None, t) == set(), t
    bare = SessionLocal()
    try:
        assert bare.execute(text("SELECT count(*) FROM settings")).scalar() == 0
    finally:
        bare.close()


def test_a_malformed_variable_fails_closed(two):
    with engine.connect() as conn:
        conn.execute(text("SELECT set_config('myfinance.user_id', 'not-a-uuid', true)"))
        with pytest.raises(DBAPIError):
            conn.execute(text("SELECT count(*) FROM assets"))


# --- writes ------------------------------------------------------------------------------

def _sample(table: str, user: uuid.UUID) -> dict:
    t = _raw(table)
    with owner_engine().connect() as conn:
        return dict(conn.execute(select(t).where(t.c.user_id == user)).mappings().first())


@pytest.mark.parametrize("table", [t for t in OWNED if t not in ("positions", "income_entries")])
def test_inserting_a_row_for_another_user_is_refused(two, table):
    alice, bob = two
    row = _sample(table, alice)
    row.pop("id", None)
    row["user_id"] = bob
    if table == "settings":
        row["key"] = "smuggled"
    t = _raw(table)
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.connection().execute(insert(t).values(**row))


def test_inserting_without_a_user_is_refused(two):
    alice, _ = two
    row = _sample("assets", alice)
    row.pop("id")
    t = _raw("assets")
    with engine.connect() as conn:
        with pytest.raises(ProgrammingError, match="row-level security"):
            conn.execute(insert(t).values(**row))


def test_a_user_can_still_insert_their_own_rows_with_raw_sql(two):
    alice, _ = two
    row = _sample("assets", alice)
    row.pop("id")
    row["name"] = _sealed("assets", alice, name="raw-insert")["name"]
    t = _raw("assets")
    with session_for(alice) as s:
        before = s.execute(text("SELECT count(*) FROM assets")).scalar()
        s.connection().execute(insert(t).values(**row))
        s.commit()
        assert s.execute(text("SELECT count(*) FROM assets")).scalar() == before + 1
        assert "raw-insert" in [a.name for a in s.query(Asset).all()]  # and it reads back, decrypted


@pytest.mark.parametrize("table", ["assets", "expenses", "reports", "insights", "monthly_records", "income_sources"])
def test_updating_a_row_to_another_users_id_is_refused(two, table):
    alice, bob = two
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.execute(text(f'UPDATE "{table}" SET user_id = :b'), {"b": bob})


def test_settings_cannot_be_handed_to_another_user(two):
    alice, bob = two
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.execute(text("UPDATE settings SET user_id = :b"), {"b": bob})


def test_updating_or_deleting_another_users_rows_touches_nothing(two):
    alice, bob = two
    with session_for(alice) as s:
        for t in OWNED:
            n = s.execute(text(f'UPDATE "{t}" SET user_id = user_id WHERE user_id = :b'), {"b": bob}).rowcount
            assert n == 0, t
        assert s.execute(text("DELETE FROM assets WHERE user_id = :b"), {"b": bob}).rowcount == 0
        assert s.execute(text("DELETE FROM settings")).rowcount == 1  # her own, and only that
        s.rollback()
    assert _owner("SELECT count(*) FROM assets WHERE user_id = :b", b=bob)[0][0] == 1
    assert _owner("SELECT count(*) FROM settings WHERE user_id = :b", b=bob)[0][0] == 1


# --- the users table ------------------------------------------------------------------------

def test_a_user_sees_and_updates_only_their_own_user_row(two):
    alice, bob = two
    with session_for(alice) as s:
        assert [r[0] for r in s.execute(text("SELECT id FROM users"))] == [alice]
        assert s.execute(
            text("UPDATE users SET terms_version = 1 WHERE id = :i"), {"i": alice}
        ).rowcount == 1
        assert s.execute(
            text("UPDATE users SET terms_version = 1 WHERE id = :i"), {"i": bob}
        ).rowcount == 0
        s.commit()


def test_the_runtime_role_cannot_create_delete_or_rewrite_users(two):
    alice, bob = two
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("INSERT INTO users (id, subject_hash, created_at) VALUES (:i, :h, now())"),
                      {"i": uuid.uuid4(), "h": "c" * 64})
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("DELETE FROM users WHERE id = :i"), {"i": alice})
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("UPDATE users SET subject_hash = :h WHERE id = :i"), {"h": "d" * 64, "i": alice})
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("UPDATE users SET id = :n WHERE id = :i"), {"n": uuid.uuid4(), "i": alice})


# --- composite foreign keys -----------------------------------------------------------------

def _position(user: uuid.UUID, asset: int) -> dict:
    return _sealed("positions", user, user_id=user, asset_id=asset, amount=1, currency="PLN", value_in_base=1,
                   price_used=1, base_currency="PLN", notes="", timestamp=datetime(2026, 1, 1))


def test_a_position_cannot_point_at_another_users_asset(two):
    alice, bob = two
    bob_asset = _owner("SELECT id FROM assets WHERE user_id = :u", u=bob)[0][0]
    t = _raw("positions")
    # As Alice, claiming to be Alice: row-level security lets her insert it, and
    # the foreign key is what refuses.
    with session_for(alice) as s:
        with pytest.raises(IntegrityError, match="fk_positions_user_asset"):
            s.connection().execute(insert(t).values(**_position(alice, bob_asset)))
    # As Alice, claiming to be Bob: row-level security.
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="row-level security"):
            s.connection().execute(insert(t).values(**_position(bob, bob_asset)))


def test_the_composite_key_holds_without_row_level_security_too(two):
    """The owner is admitted by RLS everywhere, so this is the database's own
    integrity rule and nothing else."""
    alice, bob = two
    bob_asset = _owner("SELECT id FROM assets WHERE user_id = :u", u=bob)[0][0]
    t = _raw("positions")
    with owner_engine().connect() as conn:
        with pytest.raises(IntegrityError, match="fk_positions_user_asset"):
            conn.execute(insert(t).values(**_position(alice, bob_asset)))


def test_an_income_entry_cannot_point_at_another_users_source(two):
    alice, bob = two
    bob_source = _owner("SELECT id FROM income_sources WHERE user_id = :u", u=bob)[0][0]
    t = _raw("income_entries")
    values = _sealed("income_entries", alice, user_id=alice, source_id=bob_source, month="2026-09", amount=1,
                     costs=0, notes="", updated_at=datetime(2026, 1, 1))
    with session_for(alice) as s:
        with pytest.raises(IntegrityError, match="fk_income_entries_user_source"):
            s.connection().execute(insert(t).values(**values))
    with owner_engine().connect() as conn:
        with pytest.raises(IntegrityError, match="fk_income_entries_user_source"):
            conn.execute(insert(t).values(**values))


def test_repointing_an_existing_child_at_another_users_parent_is_refused(two):
    alice, bob = two
    bob_asset = _owner("SELECT id FROM assets WHERE user_id = :u", u=bob)[0][0]
    with session_for(alice) as s:
        with pytest.raises(IntegrityError, match="fk_positions_user_asset"):
            s.execute(text("UPDATE positions SET asset_id = :a"), {"a": bob_asset})


def test_a_users_own_parent_is_accepted(two):
    alice, _ = two
    with session_for(alice) as s:
        asset = s.execute(text("SELECT id FROM assets")).scalar_one()
        s.connection().execute(insert(_raw("positions")).values(**_position(alice, asset)))
        s.commit()


def test_the_parent_unique_constraints_exist(two):
    names = {r[0] for r in _owner("SELECT conname FROM pg_constraint WHERE contype IN ('u', 'f')")}
    assert {"uq_assets_user_id_id", "uq_income_sources_user_id_id",
            "fk_positions_user_asset", "fk_income_entries_user_source"} <= names


# --- pooled connections never carry a user over ----------------------------------------------------

def test_a_pooled_connection_forgets_the_user_when_the_transaction_ends(two):
    alice, bob = two
    engine.dispose()
    with session_for(alice) as s:
        pid = s.execute(text("SELECT pg_backend_pid()")).scalar()
        assert s.execute(text("SELECT current_setting('myfinance.user_id')")).scalar() == str(alice)
        s.commit()
    # The pool hands the same server connection to the next caller...
    with engine.connect() as conn:
        assert conn.execute(text("SELECT pg_backend_pid()")).scalar() == pid
        # ...which finds no variable, and so no rows.
        assert conn.execute(text("SELECT current_setting('myfinance.user_id', true)")).scalar() in (None, "")
        assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 0
    # A session with no user on that connection is no better off.
    with open_system_session() as s:
        assert s.execute(text("SELECT pg_backend_pid()")).scalar() == pid
        assert s.execute(text("SELECT count(*) FROM assets")).scalar() == 0
    # And Bob, on it, sees Bob.
    with session_for(bob) as s:
        assert s.execute(text("SELECT pg_backend_pid()")).scalar() == pid
        assert {r[0] for r in s.execute(text("SELECT user_id FROM assets"))} == {bob}


def test_the_variable_is_set_at_the_start_of_every_transaction_of_a_session(two):
    alice, _ = two
    with session_for(alice) as s:
        for _ in range(3):
            assert {r[0] for r in s.execute(text("SELECT user_id FROM assets"))} == {alice}
            s.commit()
        s.execute(text("SELECT 1"))
        s.rollback()
        assert {r[0] for r in s.execute(text("SELECT user_id FROM assets"))} == {alice}


def test_a_variable_left_on_a_connection_for_the_whole_session_is_overridden(two):
    """If something ever did `SET myfinance.user_id` (not LOCAL) on a pooled
    connection, the next transaction still writes its own value first."""
    alice, bob = two
    engine.dispose()
    with engine.connect() as conn:
        pid = conn.execute(text("SELECT pg_backend_pid()")).scalar()
        conn.execute(text("SELECT set_config('myfinance.user_id', :u, false)"), {"u": str(alice)})
        conn.commit()
    with session_for(bob) as s:
        assert s.execute(text("SELECT pg_backend_pid()")).scalar() == pid
        assert {r[0] for r in s.execute(text("SELECT user_id FROM assets"))} == {bob}
    with open_system_session() as s:
        assert s.execute(text("SELECT count(*) FROM assets")).scalar() == 0
    engine.dispose()


def test_concurrent_requests_for_different_users_never_see_each_other(two):
    alice, bob = two
    engine.dispose()
    failures: list[str] = []

    def work(user, other):
        try:
            for _ in range(25):
                with session_for(user) as s:
                    seen = {r[0] for r in s.execute(text("SELECT user_id FROM assets"))}
                    s.commit()
                    seen |= {r[0] for r in s.execute(text("SELECT user_id FROM positions"))}
                if seen != {user}:
                    failures.append(f"{user} saw {seen}")
        except Exception as exc:  # pragma: no cover
            failures.append(repr(exc))

    threads = [threading.Thread(target=work, args=pair) for pair in [(alice, bob), (bob, alice)] * 4]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures == []


# --- the narrow doors ------------------------------------------------------------------------------------

def test_user_creation_works_for_the_runtime_role_and_provisions_assets(db):
    uid = make_user("e" * 64, provision=True)
    assert make_user("e" * 64, provision=True) == uid
    with session_for(uid) as s:
        assert s.execute(text("SELECT count(*) FROM assets")).scalar() == 9
    assert _owner("SELECT count(*) FROM users WHERE subject_hash = :h", h="e" * 64)[0][0] == 1


def test_two_first_requests_from_one_person_create_one_user(db):
    ids: list[uuid.UUID] = []
    errors: list[str] = []

    def first_request():
        try:
            ids.append(make_user("f" * 64, provision=True))
        except Exception as exc:  # pragma: no cover
            errors.append(repr(exc))

    threads = [threading.Thread(target=first_request) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(set(ids)) == 1
    # Created once, provisioned once.
    assert _owner("SELECT count(*) FROM users WHERE subject_hash = :h", h="f" * 64)[0][0] == 1
    assert _owner("SELECT count(*) FROM assets WHERE user_id = :u", u=ids[0])[0][0] == 9


def test_the_user_function_rejects_anything_but_a_hash(db):
    with engine.connect() as conn:
        for bad in ("short", "A" * 64, "g" * 64, ""):
            with pytest.raises(DBAPIError, match="subject hash"):
                conn.execute(text(f"SELECT * FROM public.{rls.GET_OR_CREATE_USER}(:h, :i, :s, :w, :v)"),
                             {"h": bad, "i": uuid.uuid4(), "s": b"", "w": b"", "v": 1})
            conn.rollback()


def test_the_functions_are_executable_by_the_runtime_role_only(db):
    rows = _owner(
        "SELECT p.proname, p.prosecdef, pg_get_userbyid(p.proowner), "
        "       has_function_privilege('public', p.oid, 'EXECUTE'), "
        "       has_function_privilege(:rt, p.oid, 'EXECUTE'), p.proconfig "
        "FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND p.proname LIKE 'myfinance_%'",
        rt=engine.url.username,
    )
    assert {r[0] for r in rows} == {
        rls.GET_OR_CREATE_USER, rls.SWEEP_JOBS, rls.RECOVERY_LOOKUP, rls.RECOVER_ACCOUNT, rls.CONTACT_UNSUBSCRIBE,
    }
    owner_name = _owner("SELECT current_user")[0][0]
    for name, definer, owner, public, runtime, config in rows:
        assert definer is True, name
        assert owner == owner_name, name
        assert public is False, name
        assert runtime is True, name
        assert any(c.startswith("search_path=") for c in config), name


def test_the_sweep_works_across_users_for_the_runtime_role(two):
    from src.models.jobnotes import (
        INTERRUPTED, INTERRUPTED_NOTE, TRANSLATION_INTERRUPTED, TRANSLATION_INTERRUPTED_NOTE,
    )
    from src.services.llm_queue import cleanup_interrupted_jobs

    alice, bob = two
    for user, tag in ((alice, "a"), (bob, "b")):
        with session_for(user) as s:
            s.add_all([
                Report(status="running"),
                Report(status="translating", content=f"{tag} english"),
                Report(status="done", content="kept"),
                Insight(kind="digest", status="pending"),
                Insight(kind="digest", status="translating", content=f"{tag} english"),
            ])
            s.commit()
    cleanup_interrupted_jobs()
    # Status and a plaintext note code only: the SQL function holds no key.
    for table in ("reports", "insights"):
        for status, note in _owner(f'SELECT status, status_note FROM "{table}"'):
            assert (status, note) in {
                ("failed", INTERRUPTED), ("done", TRANSLATION_INTERRUPTED), ("done", ""),
            }
    # What a user reads is the text for that code - and finished work, and every
    # other column of the row, is untouched.
    for user, tag in ((alice, "a"), (bob, "b")):
        with session_for(user) as s:
            reports = {r.content: r for r in s.query(Report).all() if r.content}
            assert reports[f"{tag} english"].status == "done"
            assert reports[f"{tag} english"].error == TRANSLATION_INTERRUPTED_NOTE
            assert reports["kept"].status == "done" and reports["kept"].error == ""
            running = [r for r in s.query(Report).all() if not r.content and r.status == "failed"]
            # (_populate's own pending Report is among them)
            assert len(running) == 2 and {r.error for r in running} == {INTERRUPTED_NOTE}
    assert {r[0] for r in _owner("SELECT user_id FROM reports")} == {alice, bob}


# --- the owner, and FORCE ------------------------------------------------------------------------------------

def test_the_owner_is_admitted_by_a_named_policy_and_by_nothing_else(two):
    alice, bob = two
    with owner_engine().connect() as conn:
        # Admitted: no variable, sees everyone.
        assert {r[0] for r in conn.execute(text("SELECT user_id FROM assets"))} == {alice, bob}
        # FORCE is what makes that depend on the policy: without it the owner
        # sees nothing, like anyone else.
        conn.execute(text(f"DROP POLICY {rls.OWNER_POLICY} ON assets"))
        assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 0
        conn.rollback()
        # Whereas with FORCE off the owner would be admitted implicitly.
        conn.execute(text(f"DROP POLICY {rls.OWNER_POLICY} ON assets"))
        conn.execute(text("ALTER TABLE assets NO FORCE ROW LEVEL SECURITY"))
        assert conn.execute(text("SELECT count(*) FROM assets")).scalar() == 2
        conn.rollback()


def test_the_runtime_role_is_refused_if_it_were_a_member_of_the_owner(two):
    with pytest.raises(schema.SchemaError, match="would not be subject"):
        schema.grant_runtime_role(owner_engine().url.username, owner_engine())


# --- the tests above would notice a missing policy -------------------------------------------------------------------

@pytest.mark.parametrize(
    "mutation",
    [
        "ALTER TABLE positions DISABLE ROW LEVEL SECURITY",
        f"DROP POLICY {rls.ISOLATION_POLICY} ON positions",
        f"ALTER POLICY {rls.ISOLATION_POLICY} ON positions USING (true) WITH CHECK (true)",
        f"ALTER POLICY {rls.ISOLATION_POLICY} ON positions "
        "USING (user_id IS NOT NULL) WITH CHECK (user_id IS NOT NULL)",
    ],
    ids=["rls-disabled", "policy-dropped", "policy-always-true", "policy-too-broad"],
)
def test_the_isolation_checks_fail_when_a_policy_is_weakened(two, mutation):
    alice, bob = two
    assert isolation_problems(alice, bob) == []
    try:
        _owner(mutation)
        problems = isolation_problems(alice, bob)
        assert problems, f"{mutation!r} went unnoticed"
        assert all(p.startswith("positions:") for p in problems)
    finally:
        schema.secure_postgresql(owner_engine())
    assert isolation_problems(alice, bob) == []


# --- applying it twice ----------------------------------------------------------------------------------------------------

def _catalog() -> list:
    return [
        _owner("SELECT tablename, policyname, permissive, roles::text, cmd, qual, with_check FROM pg_policies ORDER BY 1, 2"),
        _owner("SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
               "WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' ORDER BY 1"),
        _owner("SELECT proname, prosecdef, md5(prosrc), proconfig::text, proacl::text FROM pg_proc "
               "WHERE pronamespace = 'public'::regnamespace AND proname LIKE 'myfinance_%' ORDER BY 1"),
    ]


def test_applying_row_security_again_changes_nothing(two):
    before = _catalog()
    schema.secure_postgresql(owner_engine())
    schema.secure_postgresql(owner_engine())
    assert _catalog() == before
    # Even the grants survive being re-run.
    schema.grant_runtime_role(engine.url.username, owner_engine())
    schema.grant_runtime_role(engine.url.username, owner_engine())
    assert _catalog() == before
    alice, bob = two
    assert isolation_problems(alice, bob) == []


def test_users_privileges_are_narrower_than_the_other_tables(two):
    rt = engine.url.username
    rows = _owner(
        "SELECT has_table_privilege(:r, 'users', 'SELECT'), has_table_privilege(:r, 'users', 'INSERT'), "
        "has_table_privilege(:r, 'users', 'DELETE'), has_table_privilege(:r, 'users', 'UPDATE'), "
        "has_column_privilege(:r, 'users', 'terms_version', 'UPDATE'), "
        "has_column_privilege(:r, 'users', 'subject_hash', 'UPDATE')",
        r=rt,
    )[0]
    assert tuple(rows) == (True, False, False, False, True, False)
    # The columns a user's own requests keep up to date (RLS limits them to the
    # caller's row) - and the identity hash, the id and the creation time are not among them.
    keep = _owner(
        "SELECT " + ", ".join(
            f"has_column_privilege(:r, 'users', '{c}', 'UPDATE')"
            for c in ("wrapped_dek", "key_salt", "kek_version", "recovery_wrapped_dek", "recovery_failures",
                      "recovery_locked_until", "birth_year", "id", "created_at")
        ),
        r=rt,
    )[0]
    assert tuple(keep) == (True,) * 7 + (False, False)
    # key_check: readable, never writable, by the runtime role.
    kc = _owner(
        "SELECT has_table_privilege(:r, 'key_check', 'SELECT'), has_table_privilege(:r, 'key_check', 'INSERT'), "
        "has_table_privilege(:r, 'key_check', 'UPDATE'), has_table_privilege(:r, 'key_check', 'DELETE')",
        r=rt,
    )[0]
    assert tuple(kc) == (True, False, False, False)


# --- key material, recovery and contacts through the runtime role ---------------------------------------

def test_a_user_can_update_their_own_key_columns_and_nobody_elses(two):
    alice, bob = two
    with session_for(alice) as s:
        assert s.execute(text("UPDATE users SET kek_version = kek_version WHERE id = :i"), {"i": alice}).rowcount == 1
        assert s.execute(text("UPDATE users SET kek_version = kek_version WHERE id = :i"), {"i": bob}).rowcount == 0
        assert s.execute(text("UPDATE users SET wrapped_dek = NULL WHERE id = :i"), {"i": bob}).rowcount == 0
        s.rollback()
    with session_for(alice) as s:
        with pytest.raises(ProgrammingError, match="permission denied"):
            s.execute(text("UPDATE key_check SET kek_version = kek_version"))
    with session_for(alice) as s:
        assert s.execute(text("SELECT count(*) FROM key_check")).scalar() >= 1


def _proof_and_code(user: uuid.UUID):
    """Give `user` a recovery code (as the application would) and return it with
    the proof the database checks it against."""
    from src.crypto import recovery as code_crypto
    from src.services import recovery as service

    with session_for(user) as s:
        code = service.create(s, _RINGS[user])
    parsed = code_crypto.parse(code)
    with session_for(user) as s:
        salt, kdf = s.execute(text("SELECT recovery_salt, recovery_kdf FROM users WHERE id = :i"), {"i": user}).one()
    _, proof = code_crypto.derive(parsed.secret, bytes(salt), kdf)
    return code, parsed.recovery_id, proof


def _recover(as_user, recovery_id: str, proof: bytes):
    from sqlalchemy import LargeBinary, bindparam

    with session_for(as_user) as s:
        row = s.execute(
            text(f"SELECT out_status, out_user_id FROM public.{rls.RECOVER_ACCOUNT}(:r, :p, :s, :w, :v)").bindparams(
                bindparam("p", type_=LargeBinary), bindparam("s", type_=LargeBinary), bindparam("w", type_=LargeBinary)),
            {"r": recovery_id, "p": proof, "s": b"\x01" * 16, "w": b"\x02" * 60, "v": 2},
        ).one()
        s.commit()
        return tuple(row)


def test_the_recovery_function_moves_nothing_without_the_proof(two):
    alice, bob = two
    _, rid, proof = _proof_and_code(alice)
    carol = make_user("c" * 64)  # a new, empty account
    before = _owner("SELECT id, subject_hash FROM users ORDER BY id")
    for bad_proof in (b"", b"\x00" * 32, proof[:-1] + bytes([proof[-1] ^ 1])):
        assert _recover(carol, rid, bad_proof) == ("denied", None)
    assert _recover(carol, "0" * 16, proof) == ("denied", None)  # unknown id
    # No caller identity at all: refused as well, even with the right proof.
    with open_system_session() as s:
        from sqlalchemy import LargeBinary, bindparam

        row = s.execute(
            text(f"SELECT out_status FROM public.{rls.RECOVER_ACCOUNT}(:r, :p, :s, :w, :v)").bindparams(
                bindparam("p", type_=LargeBinary), bindparam("s", type_=LargeBinary), bindparam("w", type_=LargeBinary)),
            {"r": rid, "p": proof, "s": b"\x01" * 16, "w": b"\x02" * 60, "v": 2},
        ).one()
        assert row[0] == "denied"
    assert _owner("SELECT id, subject_hash FROM users ORDER BY id") == before


def test_the_recovery_function_will_not_delete_an_account_that_holds_data(two):
    alice, bob = two
    _, rid, proof = _proof_and_code(alice)
    # Bob is a user with data of his own (every table has a row): the right proof
    # from *his* session still does not let alice's account replace his.
    before = _owner("SELECT id FROM users ORDER BY id")
    assert _recover(bob, rid, proof) == ("not_empty", alice)
    assert _owner("SELECT id FROM users ORDER BY id") == before


def test_the_recovery_function_moves_the_identity_for_an_empty_account(two):
    alice, _ = two
    _, rid, proof = _proof_and_code(alice)
    carol = make_user("c" * 64, provision=True)  # new account: nine default assets, nothing else
    status, old = _recover(carol, rid, proof)
    assert (status, old) == ("recovered", alice)
    assert _owner("SELECT count(*) FROM users WHERE id = :c", c=carol)[0][0] == 0
    assert _owner("SELECT count(*) FROM assets WHERE user_id = :c", c=carol)[0][0] == 0
    assert _owner("SELECT subject_hash FROM users WHERE id = :a", a=alice)[0][0] == "c" * 64
    assert _owner("SELECT kek_version, key_salt FROM users WHERE id = :a", a=alice)[0] == (2, b"\x01" * 16)


def test_the_recovery_lookup_answers_only_for_a_known_id(two):
    alice, _ = two
    _, rid, _ = _proof_and_code(alice)
    with session_for(alice) as s:
        found = s.execute(text(f"SELECT out_user_id, out_kdf FROM public.{rls.RECOVERY_LOOKUP}(:r)"), {"r": rid}).all()
        assert [r[0] for r in found] == [alice] and found[0][1].startswith("scrypt:")
        assert s.execute(text(f"SELECT * FROM public.{rls.RECOVERY_LOOKUP}(:r)"), {"r": "nope"}).all() == []


def test_the_unsubscribe_function_touches_only_the_row_the_token_names(two, monkeypatch):
    from src.crypto import contacts
    import base64
    from sqlalchemy import LargeBinary, bindparam

    from src.config import settings

    alice, bob = two
    monkeypatch.setattr(settings, "contact_key", base64.urlsafe_b64encode(bytes(range(32))).decode())
    if True:
        for user in (alice, bob):
            token = contacts.unsubscribe_token(user, 1)
            with session_for(user) as s:
                row = s.get(UserContact, user)
                row.email = contacts.seal_email(user, f"{user}@example.test")
                row.notify_opt_in = True
                row.unsubscribe_token_hash = contacts.token_hash(token)
                s.commit()
        token = contacts.unsubscribe_token(alice, 1)
        with engine.begin() as conn:  # no user at all: the runtime role, signed in as nobody
            fn = text(f"SELECT public.{rls.CONTACT_UNSUBSCRIBE}(:h)").bindparams(bindparam("h", type_=LargeBinary))
            assert conn.execute(fn, {"h": contacts.token_hash(token)}).scalar() == 1
            assert conn.execute(fn, {"h": b"\x00" * 32}).scalar() == 0
            assert conn.execute(fn, {"h": None}).scalar() == 0
        rows = {r[0]: (r[1], r[2]) for r in _owner("SELECT user_id, notify_opt_in, email IS NULL FROM user_contacts")}
        assert rows[alice] == (False, True) and rows[bob] == (True, False)
