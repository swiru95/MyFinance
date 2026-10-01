"""Finding and creating users.

A user row is created on that person's first authenticated request - there is
no sign-up step and nothing to pre-provision. It holds an opaque id and the
subject hash (see identity.py), never a name or an email.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import Uuid, bindparam, select, text
from sqlalchemy.exc import IntegrityError

from .. import rls

from ..identity import LOCAL_USER_ID, local_subject_hash
from ..models.asset import Asset
from ..models.user import User
from ..scoping import open_session

log = logging.getLogger(__name__)


def default_assets(user_id: uuid.UUID) -> list[Asset]:
    """The asset types a brand-new wallet starts with."""
    return [
        Asset(user_id=user_id, **fields)
        for fields in (
            dict(name="Cash", kind="currency", category="Cash", profile="safe", icon="💵", units=""),
            dict(name="Gold", kind="gold", category="Gold", profile="moderate", icon="🥇", units="g"),
            dict(name="Stocks", kind="currency", category="Stocks", profile="risky", icon="📈", units=""),
            dict(name="TFI Funds", kind="currency", category="TFI", profile="moderate", icon="🏦", units=""),
            dict(name="National Bonds", kind="currency", category="Bonds", profile="safe", icon="📜", units=""),
            dict(name="Watches", kind="currency", category="Watches", profile="illiquid", icon="⌚", units=""),
            dict(name="Bitcoin", kind="crypto", category="Crypto", profile="risky", icon="₿", units="BTC"),
            dict(name="Solana", kind="crypto", category="Crypto", profile="risky", icon="◎", units="SOL"),
            dict(name="Savings", kind="currency", category="Savings", profile="safe", icon="🏧", units=""),
        )
    ]


def _find_or_add(db, subject_hash: str, candidate: uuid.UUID) -> tuple[uuid.UUID, bool]:
    """(id, created): the user with this hash, adding them as `candidate` if new.

    On PostgreSQL the application's role cannot read the users table beyond its
    own row, nor insert into it, so this goes through the SECURITY DEFINER
    function that does exactly this (rls.py). Elsewhere there is no such
    boundary and it is a plain select and insert.
    """
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text(f"SELECT out_user_id, out_created FROM public.{rls.GET_OR_CREATE_USER}(:h, :i)")
            .bindparams(bindparam("i", type_=Uuid)),
            {"h": subject_hash, "i": candidate},
        ).one()
        return row.out_user_id, row.out_created
    found = db.execute(select(User.id).where(User.subject_hash == subject_hash)).scalar_one_or_none()
    if found is not None:
        return found, False
    db.add(User(id=candidate, subject_hash=subject_hash))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        found = db.execute(select(User.id).where(User.subject_hash == subject_hash)).scalar_one_or_none()
        if found is None:
            raise
        return found, False
    return candidate, True


def get_or_create_user(
    subject_hash: str,
    *,
    user_id: uuid.UUID | None = None,
    provision: bool = True,
) -> uuid.UUID:
    """The id of the user with this subject hash, creating them if new.

    New users get the default asset types in the same transaction, so a user
    never exists half set up. Advanced features need no row: an absent
    `features` setting already means "all off" (routes/helpers.get_features).

    The session is opened as the id a *new* user would get, so that the default
    assets - which are that user's rows - can be added in the same transaction
    that creates them, under the same row-level-security variable every other
    request uses. For a returning user nothing is written and the candidate id
    is simply unused.

    Two first requests from the same person can arrive together (the SPA fires
    a page's worth of calls at once), so losing the unique-constraint race is
    expected and just means "the other one created them".
    """
    candidate = user_id or uuid.uuid4()
    db = open_session(candidate)
    try:
        found, created = _find_or_add(db, subject_hash, candidate)
        if not created:
            return found
        if provision:
            db.add_all(default_assets(found))
        db.commit()
        # The id only - never the hash input.
        log.info("created user %s", found)
        return found
    finally:
        db.close()


def get_or_create_local_user(*, provision: bool = True) -> uuid.UUID:
    """The one fixed user of an unauthenticated (local development) instance."""
    return get_or_create_user(local_subject_hash(), user_id=LOCAL_USER_ID, provision=provision)
