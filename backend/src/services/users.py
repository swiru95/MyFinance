"""Finding, creating and unlocking users.

A user row is created on that person's first authenticated request - there is
no sign-up step and nothing to pre-provision. It holds an opaque id, the subject
hash (see identity.py) and the user's *wrapped* data key (crypto/core.py), never
a name or an email.

`login` is the one door: given the subject hash and the user's secret (the token
claim that goes into their key), it returns who they are *and their key ring* -
the unwrapped data key, in memory, for this request. The row alone, or the
KEK alone, is not enough to produce it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import Uuid, bindparam, select, text, update
from sqlalchemy.exc import IntegrityError

from .. import rls
from ..crypto.core import (
    LOCAL_SECRET,
    DecryptionError,
    KekSet,
    KeyRing,
    active_keks,
    new_dek,
    new_salt,
    unwrap_dek,
    wrap_dek,
)
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


@dataclass(frozen=True)
class KeyRecord:
    """A users row as far as key handling is concerned."""

    user_id: uuid.UUID
    created: bool
    salt: bytes | None
    wrapped: bytes | None
    kek_version: int | None


@dataclass
class Account:
    """The outcome of signing in.

    `keyring` is None - and `locked` True - when the user exists but this
    sign-in cannot unlock their key: the token's claim is not the one their key
    was wrapped with (the identity changed). Everything but the recovery
    endpoints refuses such an account; see routes/recovery.py.
    """

    user_id: uuid.UUID
    keyring: KeyRing | None
    created: bool = False
    locked: bool = False
    kek_version: int | None = None
    rewrapped: bool = False


def _find_or_add(
    db, subject_hash: str, candidate: uuid.UUID, salt: bytes, wrapped: bytes, kek_version: int
) -> KeyRecord:
    """The user with this hash, adding them as `candidate` (with this wrapped
    key) if new.

    On PostgreSQL the application's role cannot read the users table beyond its
    own row, nor insert into it, so this goes through the SECURITY DEFINER
    function that does exactly this (rls.py). Elsewhere there is no such
    boundary and it is a plain select and insert.
    """
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text(
                "SELECT out_user_id, out_created, out_salt, out_wrapped, out_kek_version "
                f"FROM public.{rls.GET_OR_CREATE_USER}(:h, :i, :s, :w, :v)"
            ).bindparams(bindparam("i", type_=Uuid)),
            {"h": subject_hash, "i": candidate, "s": salt, "w": wrapped, "v": kek_version},
        ).one()
        return KeyRecord(row.out_user_id, row.out_created, row.out_salt, row.out_wrapped, row.out_kek_version)

    def existing() -> KeyRecord | None:
        row = db.execute(
            select(User.id, User.key_salt, User.wrapped_dek, User.kek_version).where(
                User.subject_hash == subject_hash
            )
        ).first()
        return KeyRecord(row[0], False, row[1], row[2], row[3]) if row else None

    found = existing()
    if found is not None:
        return found
    db.add(
        User(
            id=candidate,
            subject_hash=subject_hash,
            key_salt=salt,
            wrapped_dek=wrapped,
            kek_version=kek_version,
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        found = existing()
        if found is None:
            raise
        return found
    return KeyRecord(candidate, True, salt, wrapped, kek_version)


def _unwrap(record: KeyRecord, secret: str, keks: KekSet, expires_at: float | None) -> KeyRing:
    dek = unwrap_dek(
        record.wrapped,
        user_id=record.user_id,
        kek=keks.get(record.kek_version),
        kek_version=record.kek_version,
        salt=record.salt,
        secret=secret,
    )
    return KeyRing(record.user_id, dek, expires_at)


def _adopt_keyless(user_id: uuid.UUID, secret: str, keks: KekSet, expires_at: float | None) -> Account:
    """A user that predates encryption and has no key yet: give them one.

    The schema job gives the bootstrap user theirs while it encrypts their rows;
    anyone else who has a row but no data (it refuses to run while another user
    holds plaintext) gets a key here, on first sign-in. Conditional on there
    still being none, so two requests racing agree on the winner's.
    """
    salt, dek = new_salt(), new_dek()
    wrapped = wrap_dek(
        dek, user_id=user_id, kek=keks.current_key, kek_version=keks.current, salt=salt, secret=secret
    )
    db = open_session(user_id)
    try:
        won = db.execute(
            update(User)
            .where(User.id == user_id, User.wrapped_dek.is_(None))
            .values(key_salt=salt, wrapped_dek=wrapped, kek_version=keks.current)
        ).rowcount
        db.commit()
        if won:
            log.info("created the data key of existing user %s", user_id)
            return Account(user_id, KeyRing(user_id, dek, expires_at), kek_version=keks.current)
        row = db.execute(
            select(User.key_salt, User.wrapped_dek, User.kek_version).where(User.id == user_id)
        ).one()
    finally:
        db.close()
    record = KeyRecord(user_id, False, row[0], row[1], row[2])
    return _unlock_existing(record, secret, keks, expires_at)


def _unlock_existing(record: KeyRecord, secret: str, keks: KekSet, expires_at: float | None) -> Account:
    try:
        ring = _unwrap(record, secret, keks, expires_at)
    except DecryptionError:
        # Not an error to hide: the account exists and this identity is not the
        # one that wrapped its key. The caller decides what to say (423).
        log.warning("user %s could not be unlocked with this sign-in", record.user_id)
        return Account(record.user_id, None, locked=True, kek_version=record.kek_version)
    account = Account(record.user_id, ring, kek_version=record.kek_version)
    if record.kek_version != keks.current:
        account.rewrapped = _rewrap(ring, secret, keks, record.kek_version)
        if account.rewrapped:
            account.kek_version = keks.current
    return account


def _rewrap(ring: KeyRing, secret: str, keks: KekSet, old_version: int) -> bool:
    """Lazy KEK rotation: this user's key is wrapped under an older KEK version
    than the current one, and we hold their live secret, so wrap it again now.

    A new salt is drawn too. Conditional on the version still being the old one,
    so concurrent requests do not undo each other. Failure is logged and
    harmless - the next request tries again, and the old KEK still works.
    """
    salt = new_salt()
    wrapped = wrap_dek(
        ring.export_dek(),
        user_id=ring.user_id,
        kek=keks.current_key,
        kek_version=keks.current,
        salt=salt,
        secret=secret,
    )
    db = open_session(ring.user_id)
    try:
        done = db.execute(
            update(User)
            .where(User.id == ring.user_id, User.kek_version == old_version)
            .values(key_salt=salt, wrapped_dek=wrapped, kek_version=keks.current)
        ).rowcount
        db.commit()
        if done:
            log.info("rewrapped user %s from KEK v%s to v%s", ring.user_id, old_version, keks.current)
        return bool(done)
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        log.exception("could not rewrap user %s", ring.user_id)
        return False
    finally:
        db.close()


def login(
    subject_hash: str,
    secret: str,
    *,
    expires_at: float | None = None,
    user_id: uuid.UUID | None = None,
    provision: bool = True,
) -> Account:
    """The user with this subject hash, created (with a fresh data key) if new,
    and their key ring unlocked with `secret`.

    New users get the default asset types in the same transaction, so a user
    never exists half set up. Advanced features need no row: an absent
    `features` setting already means "all off" (routes/helpers.get_features).

    The session is opened as the id a *new* user would get, with the key a new
    user would get, so that the default assets - which are that user's rows -
    can be added in the same transaction that creates them, under the same
    row-level-security variable every other request uses. For a returning user
    nothing is written and the candidate id and key are simply unused.

    Two first requests from the same person can arrive together (the SPA fires
    a page's worth of calls at once), so losing the unique-constraint race is
    expected and just means "the other one created them" - and the key that
    counts is theirs, which `_find_or_add` hands back.
    """
    keks = active_keks()
    candidate = user_id or uuid.uuid4()
    salt, dek = new_salt(), new_dek()
    wrapped = wrap_dek(
        dek, user_id=candidate, kek=keks.current_key, kek_version=keks.current, salt=salt, secret=secret
    )
    candidate_ring = KeyRing(candidate, dek, expires_at)
    db = open_session(candidate, candidate_ring)
    try:
        record = _find_or_add(db, subject_hash, candidate, salt, wrapped, keks.current)
        if record.created:
            if provision:
                db.add_all(default_assets(candidate))
            db.commit()
            # The id only - never the hash input.
            log.info("created user %s", candidate)
            return Account(candidate, candidate_ring, created=True, kek_version=keks.current)
    finally:
        db.close()
    candidate_ring.destroy()
    if record.wrapped is None:
        return _adopt_keyless(record.user_id, secret, keks, expires_at)
    return _unlock_existing(record, secret, keks, expires_at)


def local_account(*, provision: bool = True) -> Account:
    """The one fixed user of an unauthenticated (local development) instance.

    There is no token, so their "claim" is a constant (LOCAL_SECRET) and, unless
    a KEK is configured, their KEK is the public development key: the data is
    still stored encrypted, by the same code, but protected against nothing.
    """
    return login(local_subject_hash(), LOCAL_SECRET, user_id=LOCAL_USER_ID, provision=provision)


def get_or_create_local_user(*, provision: bool = True) -> uuid.UUID:
    return local_account(provision=provision).user_id
