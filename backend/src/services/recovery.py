"""The recovery code: making one, confirming it, and using it.

See crypto/recovery.py for what the code is and why it exists. In short: if a
person's `sub` changes, their next sign-in is a new, empty user and the old data
cannot be unlocked any more; the code is a second way to unwrap that data's key.
`restore` takes it from the new, empty identity: it finds the old user by the
code's id, proves the code is right, wraps the old key for the new identity,
gives the old user the new subject hash, and removes the empty new user - the
data does not move, the *identity* does.

Guessing is limited three ways. The code carries 160 random bits, so it cannot be
guessed at all; every attempt costs an scrypt run; and wrong attempts are counted
on the caller's own user row (so every replica sees the same count) and lock them
out for longer each time, while a process-wide cap bounds the scrypt work anyone
can ask of one replica.
"""
from __future__ import annotations

import collections
import hmac
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import LargeBinary, bindparam, delete, exists, select, text, update
from sqlalchemy.exc import IntegrityError

from .. import rls
from ..config import settings
from ..crypto import recovery as code_crypto
from ..crypto.core import DecryptionError, active_keks, new_salt, wrap_dek
from ..database import Base
from ..models.user import User
from ..scoping import open_session, open_system_session, owned_table_names

log = logging.getLogger(__name__)


class RecoveryError(Exception):
    """Base of the errors the routes turn into responses."""


class InvalidCode(RecoveryError):
    """The code is malformed, unknown or wrong. Deliberately one error: the
    response must not say which, or what the database does and does not hold."""


class Throttled(RecoveryError):
    def __init__(self, retry_after: int):
        super().__init__("too many attempts")
        self.retry_after = max(1, retry_after)


class NotEmpty(RecoveryError):
    """The account the code was entered on already holds data of its own."""


class AlreadyConfigured(RecoveryError):
    """A confirmed code exists and the caller did not ask to replace it."""


class NoCode(RecoveryError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, like every timestamp here


# --- the process-wide cap ---------------------------------------------------------


class _Window:
    """At most `limit` hits per `seconds`, for the whole process."""

    def __init__(self, limit: int, seconds: float):
        self.limit, self.seconds = limit, seconds
        self._hits: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def hit(self) -> None:
        now = time.monotonic()
        with self._lock:
            while self._hits and now - self._hits[0] > self.seconds:
                self._hits.popleft()
            if len(self._hits) >= self.limit:
                raise Throttled(int(self.seconds - (now - self._hits[0])) + 1)
            self._hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Each attempt runs scrypt (tens of MiB, ~100 ms); this bounds what a flood of
# attempts - from many identities, each with its own per-user counter - can ask
# of one replica.
_global = _Window(limit=30, seconds=60)


def reset_limits() -> None:
    """For tests."""
    _global.reset()


# --- state, creation, confirmation ----------------------------------------------------


def status(db, user_id: uuid.UUID) -> dict:
    user = db.get(User, user_id)
    return {
        "configured": bool(user and user.recovery_id),
        "confirmed": bool(user and user.recovery_confirmed_at),
        "created_at": user.recovery_created_at.replace(tzinfo=timezone.utc).isoformat()
        if user and user.recovery_created_at
        else None,
    }


def create(db, keyring, *, replace: bool = False) -> str:
    """Make (or replace) the caller's recovery code and return it. This is the
    only time it exists in readable form: what is stored cannot reproduce it."""
    user = db.get(User, keyring.user_id)
    if user is None:  # pragma: no cover - the caller just authenticated as them
        raise NoCode()
    if user.recovery_id and user.recovery_confirmed_at and not replace:
        raise AlreadyConfigured()
    for attempt in range(3):
        material = code_crypto.create(keyring.user_id, keyring.export_dek())
        user.recovery_id = material.recovery_id
        user.recovery_salt = material.salt
        user.recovery_kdf = material.kdf
        user.recovery_wrapped_dek = material.wrapped_dek
        user.recovery_verifier = material.verifier
        user.recovery_created_at = _now()
        user.recovery_confirmed_at = None
        try:
            db.commit()
            break
        except IntegrityError:
            # The id is unique across users and this session (row-level security)
            # cannot see theirs, so the database is the one to say it clashed -
            # 80 random bits make that all but impossible; try again.
            db.rollback()
            user = db.get(User, keyring.user_id)
            if attempt == 2:
                raise
    log.info("recovery code (re)created for user %s", keyring.user_id)
    return material.code


def _derive(user: User, parsed: code_crypto.ParsedCode):
    return code_crypto.derive(parsed.secret, user.recovery_salt, user.recovery_kdf)


def confirm(db, user_id: uuid.UUID, code: str) -> None:
    """The user has typed the code back: they hold it. Counts as an attempt (it
    runs scrypt and tests a code)."""
    _global.hit()
    user = db.get(User, user_id)
    _check_lock(user)
    try:
        parsed = code_crypto.parse(code)
        if not user.recovery_id or parsed.recovery_id != user.recovery_id:
            raise InvalidCode()
        _, proof = _derive(user, parsed)
        if not hmac.compare_digest(code_crypto.verifier_of(proof), bytes(user.recovery_verifier)):
            raise InvalidCode()
    except (code_crypto.RecoveryCodeError, InvalidCode):
        _record_failure(db, user_id)
        raise InvalidCode() from None
    user.recovery_confirmed_at = _now()
    user.recovery_failures = 0
    user.recovery_locked_until = None
    db.commit()
    log.info("recovery code confirmed for user %s", user_id)


# --- the throttle ---------------------------------------------------------------------


def _check_lock(user: User) -> None:
    until = user.recovery_locked_until
    if until is not None and until > _now():
        raise Throttled(int((until - _now()).total_seconds()) + 1)


def _record_failure(db, user_id: uuid.UUID) -> None:
    """Count a wrong attempt on the caller's own row and lock them out once they
    pass the allowance - for longer each time, up to a day."""
    db.rollback()
    db.execute(
        update(User).where(User.id == user_id).values(recovery_failures=User.recovery_failures + 1)
    )
    failures = db.execute(select(User.recovery_failures).where(User.id == user_id)).scalar_one()
    over = failures - settings.recovery_max_failures
    if over >= 0:
        seconds = min(settings.recovery_lock_seconds * (2**over), 86400)
        db.execute(
            update(User).where(User.id == user_id).values(recovery_locked_until=_now() + timedelta(seconds=seconds))
        )
    db.commit()
    log.warning("wrong recovery code from user %s (%d in a row)", user_id, failures)


# --- using it -----------------------------------------------------------------------------


@dataclass
class _Found:
    user_id: uuid.UUID
    salt: bytes
    kdf: str
    wrapped: bytes


def _lookup(db, recovery_id: str) -> _Found | None:
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text(f"SELECT out_user_id, out_salt, out_kdf, out_wrapped FROM public.{rls.RECOVERY_LOOKUP}(:r)"),
            {"r": recovery_id},
        ).first()
        return _Found(row[0], bytes(row[1]), row[2], bytes(row[3])) if row else None
    row = db.execute(
        select(User.id, User.recovery_salt, User.recovery_kdf, User.recovery_wrapped_dek).where(
            User.recovery_id == recovery_id, User.recovery_wrapped_dek.is_not(None)
        )
    ).first()
    return _Found(row[0], bytes(row[1]), row[2], bytes(row[3])) if row else None


def _apply(
    db, caller_id: uuid.UUID, recovery_id: str, proof: bytes, salt: bytes, wrapped: bytes, kek_version: int
) -> tuple[str, uuid.UUID | None]:
    """Move the identity (see module doc). One transaction; returns (status, old user id)."""
    if db.get_bind().dialect.name == "postgresql":
        row = db.execute(
            text(
                f"SELECT out_status, out_user_id FROM public.{rls.RECOVER_ACCOUNT}(:r, :p, :s, :w, :v)"
            ).bindparams(
                bindparam("p", type_=LargeBinary), bindparam("s", type_=LargeBinary), bindparam("w", type_=LargeBinary)
            ),
            {"r": recovery_id, "p": proof, "s": salt, "w": wrapped, "v": kek_version},
        ).one()
        db.commit()
        return row[0], row[1]
    # SQLite has no row-level security to get past, so the same steps are done
    # directly (by a system session, which is not confined to one user).
    db.rollback()
    system = open_system_session()
    try:
        old = system.execute(
            select(User.id, User.recovery_verifier).where(User.recovery_id == recovery_id)
        ).first()
        if old is None or old[1] is None or not hmac.compare_digest(
            code_crypto.verifier_of(proof), bytes(old[1])
        ):
            return "denied", None
        old_id = old[0]
        keys = dict(key_salt=salt, wrapped_dek=wrapped, kek_version=kek_version,
                    recovery_failures=0, recovery_locked_until=None)
        if old_id == caller_id:
            system.execute(update(User).where(User.id == old_id).values(**keys))
            system.commit()
            return "rewrapped", old_id
        tables = {name: Base.metadata.tables[name] for name in owned_table_names()}
        for name, table in tables.items():
            if name in rls.DISPOSABLE_TABLES:
                continue
            if system.execute(select(exists().where(table.c.user_id == caller_id))).scalar():
                system.rollback()
                return "not_empty", old_id
        new_hash = system.execute(select(User.subject_hash).where(User.id == caller_id)).scalar_one()
        for name in rls.DISPOSABLE_TABLES:
            if name in tables:
                system.execute(delete(tables[name]).where(tables[name].c.user_id == caller_id))
        system.execute(delete(User).where(User.id == caller_id))
        system.execute(update(User).where(User.id == old_id).values(subject_hash=new_hash, **keys))
        system.commit()
        return "recovered", old_id
    finally:
        system.close()


def restore(user_id: uuid.UUID, key_secret: str, code: str) -> str:
    """Re-attach the data a recovery code belongs to to the caller's identity.

    `user_id` is the caller (the new, empty user - or the old one itself, when
    only their key could not be unlocked) and `key_secret` their current token
    claim, which the data key is wrapped under from here on. Returns
    "recovered" or "rewrapped". After a "recovered" the caller's user row is
    gone: their next request signs in as the old user.
    """
    _global.hit()
    db = open_session(user_id)
    try:
        caller = db.get(User, user_id)
        if caller is None:  # pragma: no cover
            raise InvalidCode()
        _check_lock(caller)
        try:
            parsed = code_crypto.parse(code)
            found = _lookup(db, parsed.recovery_id)
            if found is None:
                # Spend the same time on an unknown code as a known one.
                code_crypto.derive(parsed.secret, b"\0" * code_crypto.SALT_BYTES, code_crypto.kdf_descriptor())
                raise InvalidCode()
            wrap_key, proof = code_crypto.derive(parsed.secret, found.salt, found.kdf)
            dek = code_crypto.unwrap(found.user_id, found.wrapped, wrap_key)
        except (code_crypto.RecoveryCodeError, DecryptionError, InvalidCode):
            _record_failure(db, user_id)
            raise InvalidCode() from None

        keks = active_keks()
        salt = new_salt()
        wrapped = wrap_dek(
            dek, user_id=found.user_id, kek=keks.current_key, kek_version=keks.current, salt=salt, secret=key_secret
        )
        result, old_id = _apply(db, user_id, parsed.recovery_id, proof, salt, wrapped, keks.current)
        if result == "denied":
            _record_failure(db, user_id)
            raise InvalidCode()
        if result == "not_empty":
            raise NotEmpty()
        log.info("recovery used: identity of user %s moved onto %s (%s)", user_id, old_id, result)
        return result
    finally:
        db.close()
