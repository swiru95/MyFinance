"""Automatic per-user scoping of database sessions (src/scoping.py), and the
shape every data table must have (user_id NOT NULL + FK, per-user uniques).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import aliased

from src.database import Base, SessionLocal
from src.models import (
    Asset, Expense, IncomeEntry, IncomeSource, Insight, MonthlyRecord, Owned, Position, Report, Setting, User,
)
from src.scoping import UnscopedAccess, open_session, open_system_session
from src.services.users import get_or_create_user


@pytest.fixture
def two(db):
    """(alice_id, bob_id) with one asset each, plus their sessions."""
    a = get_or_create_user("a" * 64, provision=False)
    b = get_or_create_user("b" * 64, provision=False)
    sa, sb = open_session(a), open_session(b)
    sa.add(Asset(name="alice-asset", kind="currency"))
    sb.add(Asset(name="bob-asset", kind="currency"))
    sa.commit()
    sb.commit()
    yield a, b, sa, sb
    sa.close()
    sb.close()


# --- shape of the schema ---------------------------------------------------

def test_every_data_table_is_owned_with_a_not_null_foreign_key_to_users(db):
    tables = {t.name: t for t in Base.metadata.sorted_tables}
    assert "users" in tables
    for name, table in tables.items():
        if name == "users":
            continue
        col = table.c.user_id
        assert col.nullable is False, name
        targets = {fk.target_fullname for fk in col.foreign_keys}
        assert targets == {"users.id"}, name
    # ...and every one of them carries the mixin that switches scoping on.
    assert {t.name for t in tables.values()} - {"users"} == {
        cls.__tablename__ for cls in Owned.__subclasses__()
    }


def test_the_expected_tables_are_owned():
    assert {cls for cls in Owned.__subclasses__()} == {
        Asset, Expense, IncomeEntry, IncomeSource, Insight, MonthlyRecord, Position, Report, Setting,
    }


def test_settings_primary_key_is_user_and_key():
    assert [c.name for c in Setting.__table__.primary_key.columns] == ["user_id", "key"]


def test_unique_constraints_are_per_user():
    def uniques(model):
        return {tuple(c.name for c in u.columns) for u in model.__table__.constraints
                if u.__class__.__name__ == "UniqueConstraint"}

    assert ("user_id", "month") in uniques(MonthlyRecord)
    assert ("user_id", "source_id", "month") in uniques(IncomeEntry)
    # No unique constraint or index left that is global.
    for model in (MonthlyRecord, IncomeEntry):
        for idx in model.__table__.indexes:
            assert not idx.unique


def test_user_columns():
    assert {c.name for c in User.__table__.columns} == {
        "id", "subject_hash", "created_at", "terms_version", "terms_accepted_at",
    }


def test_two_users_may_hold_the_same_month_and_setting_key(two):
    a, b, sa, sb = two
    for s in (sa, sb):
        s.add(MonthlyRecord(month="2026-03", income=1, actual_spent=1))
        s.add(Setting(key="timezone", value="UTC"))
        s.commit()
    assert sa.query(func.count(MonthlyRecord.id)).scalar() == 1
    assert sb.query(func.count(MonthlyRecord.id)).scalar() == 1


# --- reads --------------------------------------------------------------------

def test_a_session_sees_only_its_own_rows(two):
    a, b, sa, sb = two
    assert [x.name for x in sa.query(Asset).all()] == ["alice-asset"]
    assert [x.name for x in sb.query(Asset).all()] == ["bob-asset"]


def test_get_by_primary_key_of_someone_elses_row_finds_nothing(two):
    a, b, sa, sb = two
    bobs = sb.query(Asset).one()
    assert sa.get(Asset, bobs.id) is None
    assert sa.query(Asset).filter(Asset.id == bobs.id).first() is None


def test_column_and_aggregate_queries_are_scoped_too(two):
    a, b, sa, sb = two
    assert sa.query(Asset.name).all() == [("alice-asset",)]
    assert sa.query(func.count(Asset.id)).scalar() == 1
    assert sa.execute(select(func.max(Asset.id))).scalar() == sa.query(Asset).one().id


def test_joins_and_aliases_are_scoped(two):
    a, b, sa, sb = two
    asset_b = sb.query(Asset).one()
    sb.add(Position(asset_id=asset_b.id, amount=1, currency="PLN"))
    sb.commit()
    rows = sa.query(Position).join(Asset, Position.asset_id == Asset.id).all()
    assert rows == []
    al = aliased(Asset)
    assert [x.name for x in sa.query(al).all()] == ["alice-asset"]


# --- writes ---------------------------------------------------------------

def test_bulk_delete_and_update_only_touch_own_rows(two):
    a, b, sa, sb = two
    assert sa.query(Asset).filter(Asset.name == "bob-asset").delete() == 0
    assert sa.execute(update(Asset).values(name="hacked")).rowcount == 1
    sa.commit()
    assert [x.name for x in sb.query(Asset).all()] == ["bob-asset"]
    assert sa.execute(delete(Asset)).rowcount == 1
    sa.commit()
    assert sb.query(func.count(Asset.id)).scalar() == 1


def test_new_rows_are_stamped_with_the_sessions_user(two):
    a, b, sa, sb = two
    row = sa.query(Asset).one()
    assert row.user_id == a
    sa.add(Setting(key="k", value="v"))
    sa.commit()
    assert sa.query(Setting).one().user_id == a


def test_adding_a_row_that_names_another_user_is_refused(two):
    a, b, sa, sb = two
    sa.add(Asset(name="smuggled", kind="currency", user_id=b))
    with pytest.raises(UnscopedAccess):
        sa.commit()
    sa.rollback()


def test_moving_another_users_row_into_a_session_is_refused(two):
    a, b, sa, sb = two
    sysdb = open_system_session()
    foreign = sysdb.query(Asset).filter(Asset.user_id == b).one()
    sysdb.expunge(foreign)
    sysdb.close()
    sa.add(foreign)
    foreign.name = "edited"
    with pytest.raises(UnscopedAccess):
        sa.commit()
    sa.rollback()

    sysdb = open_system_session()
    foreign = sysdb.query(Asset).filter(Asset.user_id == b).one()
    sysdb.expunge(foreign)
    sysdb.close()
    sa.add(foreign)
    sa.delete(foreign)
    with pytest.raises(UnscopedAccess):
        sa.commit()
    sa.rollback()
    assert sb.query(Asset).one().name == "bob-asset"


# --- fail closed -----------------------------------------------------------------

def test_a_session_without_a_user_cannot_read_or_write_owned_tables(two):
    bare = SessionLocal()
    try:
        with pytest.raises(UnscopedAccess):
            bare.query(Asset).all()
        with pytest.raises(UnscopedAccess):
            bare.execute(select(Setting))
        bare.add(Asset(name="x", kind="currency"))
        with pytest.raises(UnscopedAccess):
            bare.commit()
    finally:
        bare.rollback()
        bare.close()


def test_a_session_without_a_user_can_still_read_users(two):
    bare = SessionLocal()
    try:
        assert bare.query(User).count() >= 2
    finally:
        bare.close()


def test_the_system_session_sees_everyone(two):
    s = open_system_session()
    try:
        assert {x.name for x in s.query(Asset).all()} == {"alice-asset", "bob-asset"}
    finally:
        s.close()


def test_open_session_needs_a_uuid():
    with pytest.raises(TypeError):
        open_session("not-a-uuid")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "build",
    [
        lambda s: s.query(Asset).count(),
        lambda s: s.execute(select(func.count()).select_from(select(Asset.id).subquery())),
        lambda s: s.execute(select(func.count()).select_from(select(Asset.id).cte())),
        lambda s: s.query(Asset).filter(Asset.id.in_(select(Asset.id))).all(),
        lambda s: s.execute(select(func.count()).select_from(Asset.__table__)),
        lambda s: s.execute(delete(Asset.__table__)),
    ],
    ids=["Query.count", "subquery", "cte", "in-select", "core-table", "core-delete"],
)
def test_constructs_that_would_escape_the_filter_are_refused(two, build):
    """Loader criteria only reach the statement's own FROM list. A nested SELECT
    would read every user's rows, so the session refuses rather than leaks."""
    a, b, sa, sb = two
    with pytest.raises(UnscopedAccess):
        build(sa)
