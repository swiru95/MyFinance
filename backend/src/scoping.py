"""Per-user scoping of every database session.

Ownership is enforced here, once, instead of in the several hundred queries
spread over routes and services. A session is opened *for one user* and from
then on:

- every SELECT, UPDATE and DELETE that touches a table inheriting `Owned` has
  `AND user_id = <that user>` added by the ORM, wherever the query was written
  (route, service, helper, background job). Another user's id therefore simply
  matches no row - which the routes already turn into a 404;
- every new row is stamped with that user's id when it is flushed, and a row
  that already names a different user is refused.

A session opened for *nobody* fails closed: touching an owned table raises
`UnscopedAccess` instead of quietly returning everyone's rows. The few places
that really do work across users (the schema job, the startup sweep of
interrupted jobs) ask for that explicitly with `open_system_session()`.

Loader criteria only reach the statement's own FROM list, so constructs that
would slip past them are refused outright instead: a Core statement on an owned
table, and any subquery/CTE/EXISTS/UNION over one (`Query.count()` is one - it
wraps the query in a subquery - so use `db.query(func.count(Model.id))`).

What this does not cover, deliberately: raw SQL (`text()`) is invisible to the
ORM hooks and must filter on `user_id` itself, and the ORM's bulk INSERT
(`session.execute(insert(Model), [...])`) is not stamped. Nothing in the
application uses either.

When PostgreSQL row-level security is added later, this is where the session
variable it needs would be set, from the same `info["user_id"]`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import event
from sqlalchemy.sql.expression import SelectBase, TableClause
from sqlalchemy.sql.visitors import iterate
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from .database import SessionLocal
from .models.user import Owned

USER_KEY = "user_id"
SYSTEM_KEY = "system"


class UnscopedAccess(RuntimeError):
    """A session with no user touched a table that belongs to users."""


def open_session(user_id: uuid.UUID) -> Session:
    """A session confined to `user_id`'s rows."""
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("open_session needs the user's UUID")
    return SessionLocal(info={USER_KEY: user_id})


def open_system_session() -> Session:
    """A session that sees every user's rows.

    For the schema job and the startup sweep only. Rows it creates must name
    their owner themselves.
    """
    return SessionLocal(info={SYSTEM_KEY: True})


def owned_table_names() -> set[str]:
    return {cls.__tablename__ for cls in Owned.__subclasses__()}


def _owned_tables_in(element, names: set[str]) -> bool:
    return any(isinstance(el, TableClause) and el.name in names for el in iterate(element))


def _has_nested_owned_select(statement, names: set[str]) -> bool:
    """A subquery, CTE, EXISTS, compound SELECT or IN (SELECT ...) over an owned
    table anywhere inside `statement`.

    The ORM's loader criteria are applied to the statement's own FROM list only;
    a SELECT nested inside it is compiled without them, so it would read every
    user's rows. That is how `Query.count()` (which wraps the query in a
    subquery) would quietly count other people's data. Rather than rely on no
    one ever writing such a query, refuse it.
    """
    for el in iterate(statement):
        if el is statement:
            continue
        if isinstance(el, SelectBase) and _owned_tables_in(el, names):
            return True
    return False


@event.listens_for(Session, "do_orm_execute")
def _scope_statement(state: ORMExecuteState) -> None:
    # A refresh of an instance this session already holds, which got there
    # through a scoped query (or was stamped on flush).
    if state.is_column_load:
        return
    info = state.session.info
    if info.get(SYSTEM_KEY):
        return
    names = owned_table_names()
    if not _owned_tables_in(state.statement, names):
        return
    user_id = info.get(USER_KEY)
    if user_id is None:
        raise UnscopedAccess(
            "this session has no user; open it with scoping.open_session(user_id) "
            "(or open_system_session() for a deliberate cross-user job)"
        )
    if _has_nested_owned_select(state.statement, names):
        raise UnscopedAccess(
            "a subquery over a user-owned table is not scoped automatically "
            "(this includes Query.count() - use func.count() as a column instead)"
        )
    if not any(issubclass(m.class_, Owned) for m in state.all_mappers):
        raise UnscopedAccess(
            "a Core statement on a user-owned table cannot be scoped automatically; "
            "query the mapped class instead"
        )
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(
                Owned,
                lambda cls: cls.user_id == user_id,
                include_aliases=True,
            )
        )


@event.listens_for(Session, "before_flush")
def _stamp_and_check(session: Session, flush_context, instances) -> None:
    info = session.info
    if info.get(SYSTEM_KEY):
        return
    user_id = info.get(USER_KEY)
    for obj in session.new:
        if not isinstance(obj, Owned):
            continue
        if user_id is None:
            raise UnscopedAccess(f"cannot add a {type(obj).__name__} to a session with no user")
        if obj.user_id is None:
            obj.user_id = user_id
        elif obj.user_id != user_id:
            raise UnscopedAccess(f"{type(obj).__name__} belongs to a different user")
    for obj in list(session.dirty) + list(session.deleted):
        if isinstance(obj, Owned) and obj.user_id != user_id:
            raise UnscopedAccess(f"{type(obj).__name__} belongs to a different user")
