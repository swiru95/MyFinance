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

A session also carries its user's *key ring* (`session.info["keyring"]`, see
database.KeyedSession and crypto/): the encrypted columns read and write
transparently under it, and a session opened without one - the system session,
a bare `SessionLocal()` - raises `KeysUnavailable` the moment it touches one.

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

On PostgreSQL this is also where the database's own copy of the rule is wired
in (see rls.py): at the start of every transaction `after_begin` runs
`set_config('myfinance.user_id', <the session's user>, true)` - transaction
local, like `SET LOCAL` - and the row-level-security policies on every owned
table compare `user_id` with it. A session with no user (or a system session)
sets it to the empty string, which matches no row. Because it is set per
transaction and reverts when the transaction ends, a pooled connection can
never carry one user's id into another user's request.
"""
from __future__ import annotations

import uuid

from sqlalchemy import event, text
from sqlalchemy.sql.expression import SelectBase, TableClause
from sqlalchemy.sql.visitors import iterate
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from . import rls
from .crypto.core import KeyRing
from .database import KEYRING_KEY, SessionLocal
from .models.user import Owned

USER_KEY = "user_id"
SYSTEM_KEY = "system"


class UnscopedAccess(RuntimeError):
    """A session with no user touched a table that belongs to users."""


def open_session(user_id: uuid.UUID, keyring: KeyRing | None = None) -> Session:
    """A session confined to `user_id`'s rows, decrypting them with `keyring`.

    Without a key ring the session can still read and write the plaintext
    columns (ids, statuses, dates and months kept in the clear), but any
    encrypted column raises `crypto.core.KeysUnavailable`: nothing here falls
    back to "no encryption".
    """
    if not isinstance(user_id, uuid.UUID):
        raise TypeError("open_session needs the user's UUID")
    if keyring is not None and keyring.user_id != user_id:
        raise ValueError("the key ring belongs to a different user than the session")
    info = {USER_KEY: user_id}
    if keyring is not None:
        info[KEYRING_KEY] = keyring
    return SessionLocal(info=info)


def open_system_session() -> Session:
    """A session that is not confined to a user by the ORM.

    For the schema job (and tests that inspect across users) only. Rows it
    creates must name their owner themselves.

    It holds no key, so it cannot read or write an encrypted column - which is
    what keeps the cross-user jobs (the startup sweep, the schema job) honest:
    they work on ids, statuses and key material only.

    This lifts the ORM's filtering and nothing else. On PostgreSQL it does not
    set the row-level-security variable, so it sees every user's rows only when
    the database role it connects as is admitted by the owner policy (the
    schema job's role is). Connected as the application's runtime role it sees
    no owned rows at all - the cross-user work the application needs there goes
    through the narrow functions in rls.py instead.
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


@event.listens_for(Session, "after_begin")
def _set_row_security_user(session: Session, transaction, connection) -> None:
    """Tell PostgreSQL whose transaction this is (see rls.py).

    Runs for every transaction the session begins, on whichever pooled
    connection it was given, and always writes the variable - to the user's id,
    or to '' for a session with none - so nothing a previous holder of the
    connection left behind can apply.
    """
    if connection.dialect.name != "postgresql":
        return
    user_id = session.info.get(USER_KEY)
    connection.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": rls.GUC, "value": "" if user_id is None else str(user_id)},
    )


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
