"""Key hierarchy and the primitives under it.

    KEK (Kubernetes Secret, versioned)  +  per-user salt (users.key_salt)
                                        +  user secret (a token claim, never stored)
        --HKDF-SHA256-->  key-wrapping key
        --AES-256-GCM--> users.wrapped_dek          (AAD: user id, KEK version)

    DEK (32 random bytes per user, stored only wrapped)
        --HKDF-SHA256(info = table name)-->  per-table subkey
        --AES-256-GCM, random nonce-->       every value (AAD: user id, table, column)

Nothing here touches the database or the network. What it guarantees:

* the database plus the KEK, without the user's token claim, cannot unwrap a
  DEK - the claim is a required input to the wrapping key;
* the database plus a user's claim, without the KEK, cannot either;
* a ciphertext cell does not decrypt anywhere but the user, table and column it
  was written for (the AAD is authenticated, so a moved cell fails its tag).

What it does not do: bind a cell to its *row*. The column types that call
`KeyRing.seal` (fields.py) see one cell at a time, and the row id of a new row
does not exist until the INSERT has run, after the value was sealed. So a cell
copied to another row of the same user and column decrypts. See README.

Key material lives in `KeyRing` objects, in memory, and nowhere else.
"""
from __future__ import annotations

import base64
import contextvars
import functools
import hashlib
import hmac
import os
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import settings

FORMAT_V1 = b"\x01"
NONCE_LEN = 12
KEY_LEN = 32
SALT_LEN = 16


class CryptoError(RuntimeError):
    """Base of everything this package raises on purpose."""


class KekError(CryptoError):
    """The KEK configuration is missing, malformed or does not match the database."""


class KeysUnavailable(CryptoError):
    """An encrypted column was touched with no user key in reach: a session that
    was opened without one (the system session), or a result consumed after the
    session operation that produced it returned. Always a bug in the caller;
    it fails closed rather than returning ciphertext or guessing a key."""


class KeyExpired(CryptoError):
    """The key ring outlived the token (or the job allowance) it was made for."""


class DecryptionError(CryptoError):
    """Wrong key, wrong user/table/column, or a tampered or truncated value."""


# --- HKDF / AEAD helpers ---------------------------------------------------


def hkdf(ikm: bytes, *, salt: bytes | None, info: bytes, length: int = KEY_LEN) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _lp(data: bytes, width: int) -> bytes:
    """Length-prefixed, so concatenated inputs cannot be re-split differently."""
    return len(data).to_bytes(width, "big") + data


def aead_seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    return FORMAT_V1 + nonce + AESGCM(key).encrypt(nonce, plaintext, aad)


def aead_open(key: bytes, blob: bytes, aad: bytes) -> bytes:
    if len(blob) < 1 + NONCE_LEN + 16 or blob[:1] != FORMAT_V1:
        raise DecryptionError("not a recognised ciphertext")
    try:
        return AESGCM(key).decrypt(blob[1 : 1 + NONCE_LEN], blob[1 + NONCE_LEN :], aad)
    except InvalidTag as exc:
        raise DecryptionError("authentication failed (wrong key, or not this user/table/column)") from exc


# --- KEK ---------------------------------------------------------------------

# Used only when authentication is off and no KEK is configured, so that a local
# `docker compose up` runs the same encrypted code path as production. It is in
# the source: it protects nothing and must never be the key of a real deployment
# (auth.validate_config refuses to start with authentication on and no KEK).
DEV_KEK_VERSION = 1
_DEV_KEK = hashlib.sha256(b"myfinance insecure development kek - not a secret").digest()

# The user secret of the fixed local user (authentication off): there is no token.
LOCAL_SECRET = "myfinance-local-development-user"


@dataclass(frozen=True)
class KekSet:
    keys: dict[int, bytes]
    current: int
    development: bool = False

    def get(self, version: int) -> bytes:
        try:
            return self.keys[version]
        except KeyError:
            raise KekError(
                f"KEK version {version} is not configured (MYFINANCE_KEKS lists "
                f"{sorted(self.keys)}); it is still needed to unwrap users on that version"
            ) from None

    @property
    def current_key(self) -> bytes:
        return self.keys[self.current]


def _b64decode(text: str) -> bytes:
    text = text.strip()
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except Exception as exc:  # binascii.Error, ValueError
        raise KekError("a key is not valid base64") from exc


def parse_keks(raw: str, current: int | None = None) -> KekSet:
    entries = [e for e in raw.replace("\n", ",").replace(";", ",").split(",") if e.strip()]
    if not entries:
        raise KekError("no KEK configured: set MYFINANCE_KEKS to `<version>:<base64 key>`")
    keys: dict[int, bytes] = {}
    for entry in entries:
        version_text, sep, key_text = entry.strip().partition(":")
        if not sep:
            raise KekError("MYFINANCE_KEKS entries look like `<version>:<base64 key>`")
        try:
            version = int(version_text)
        except ValueError:
            raise KekError("a KEK version must be a whole number") from None
        if version < 1:
            raise KekError("KEK versions start at 1")
        key = _b64decode(key_text)
        if len(key) < KEY_LEN:
            raise KekError(f"KEK version {version} is shorter than {KEY_LEN} bytes")
        if version in keys:
            raise KekError(f"KEK version {version} is listed twice")
        keys[version] = key
    chosen = current if current is not None else max(keys)
    if chosen not in keys:
        raise KekError(f"MYFINANCE_KEK_CURRENT_VERSION={chosen} is not among the configured versions")
    return KekSet(keys=keys, current=chosen)


@functools.lru_cache(maxsize=8)
def _parse_cached(raw: str, current: int | None) -> KekSet:
    return parse_keks(raw, current)


def active_keks() -> KekSet:
    """The configured KEKs, or the public development one when authentication is off."""
    from ..auth import auth_enabled  # late: auth imports services that import this

    if settings.keks.strip():
        return _parse_cached(settings.keks, settings.kek_current_version)
    if not auth_enabled():
        return KekSet(keys={DEV_KEK_VERSION: _DEV_KEK}, current=DEV_KEK_VERSION, development=True)
    raise KekError("MYFINANCE_KEKS is required when authentication is enabled")


# --- Wrapping a DEK ------------------------------------------------------------


def new_salt() -> bytes:
    return os.urandom(SALT_LEN)


def new_dek() -> bytes:
    return os.urandom(KEY_LEN)


def _wrapping_key(kek: bytes, version: int, salt: bytes, secret: str) -> bytes:
    secret_b = secret.encode("utf-8")
    if not secret_b:
        raise CryptoError("the user secret is empty")
    return hkdf(
        _lp(kek, 2) + _lp(secret_b, 4),
        salt=salt,
        info=b"myfinance/v1/key-wrapping-key|kek:%d" % version,
    )


def _dek_aad(user_id: uuid.UUID, version: int) -> bytes:
    return b"myfinance/v1/dek|" + user_id.bytes + b"|kek:%d" % version


def wrap_dek(dek: bytes, *, user_id: uuid.UUID, kek: bytes, kek_version: int, salt: bytes, secret: str) -> bytes:
    key = _wrapping_key(kek, kek_version, salt, secret)
    return aead_seal(key, dek, _dek_aad(user_id, kek_version))


def unwrap_dek(
    wrapped: bytes, *, user_id: uuid.UUID, kek: bytes, kek_version: int, salt: bytes, secret: str
) -> bytes:
    key = _wrapping_key(kek, kek_version, salt, secret)
    return aead_open(key, bytes(wrapped), _dek_aad(user_id, kek_version))


# --- KEK check value ----------------------------------------------------------

_CHECK_PLAINTEXT = b"myfinance key check value v1"


def make_key_check(kek: bytes, version: int) -> bytes:
    """Something only this exact KEK can open, stored next to the data (table
    `key_check`) so a wrong Secret is caught before anything is written under it."""
    key = hkdf(kek, salt=None, info=b"myfinance/v1/key-check")
    return aead_seal(key, _CHECK_PLAINTEXT, b"myfinance/v1/key-check|kek:%d" % version)


def verify_key_check(kek: bytes, version: int, blob: bytes) -> bool:
    key = hkdf(kek, salt=None, info=b"myfinance/v1/key-check")
    try:
        return hmac.compare_digest(
            aead_open(key, bytes(blob), b"myfinance/v1/key-check|kek:%d" % version), _CHECK_PLAINTEXT
        )
    except DecryptionError:
        return False


# --- The key ring ----------------------------------------------------------------


class KeyRing:
    """One user's unwrapped DEK, in memory, with the cipher for each table.

    Held on the database session (`session.info`), handed to the LLM queue by
    the request that starts a job, and never written anywhere. There is no cache
    of rings across requests: unwrapping costs one HKDF and one AES-GCM
    decryption, so each request does its own from the live token, and nothing
    outlives the token that unlocked it.

    `expires_at` is a unix time; past it every operation refuses.
    """

    __slots__ = ("user_id", "_dek", "_ciphers", "expires_at", "_lock")

    def __init__(self, user_id: uuid.UUID, dek: bytes, expires_at: float | None = None):
        if len(dek) != KEY_LEN:
            raise CryptoError("a DEK is 32 bytes")
        self.user_id = user_id
        self._dek: bytes | None = dek
        # table -> its AES-GCM cipher (the key derived from the DEK for that table)
        self._ciphers: dict[str, AESGCM] = {}
        self.expires_at = expires_at
        self._lock = threading.Lock()

    # -- lifecycle --

    def expired(self, now: float | None = None) -> bool:
        return self._dek is None or (
            self.expires_at is not None and (time.time() if now is None else now) >= self.expires_at
        )

    def _check(self) -> bytes:
        if self._dek is None:
            raise KeyExpired("this key ring has been destroyed")
        if self.expires_at is not None and time.time() >= self.expires_at:
            raise KeyExpired("this key ring has expired; sign in again (or generate the job again)")
        return self._dek

    def fork(self, ttl_seconds: float) -> "KeyRing":
        """A copy for a background job, valid for `ttl_seconds` from now and
        destroyed by the job. The allowance is the job's own, *not* bounded by the
        request ring's expiry: a job queued behind a long model load must be able to
        outlive the access token that started it, or most of them would fail. What
        bounds it instead is this explicit cap (MYFINANCE_JOB_KEY_SECONDS) and that
        the copy exists only in the memory of the queued closure (see README)."""
        dek = self._check()
        until = time.time() + ttl_seconds
        return KeyRing(self.user_id, dek, until)

    def destroy(self) -> None:
        """Drop the key. Python cannot scrub memory; this removes the references."""
        with self._lock:
            self._dek = None
            self._ciphers.clear()

    def export_dek(self) -> bytes:
        """The raw DEK, for wrapping it (rewrap, recovery code). Handle with care."""
        return self._check()

    # -- cells --

    def _cipher(self, table: str) -> AESGCM:
        dek = self._check()
        cipher = self._ciphers.get(table)
        if cipher is None:
            cipher = AESGCM(hkdf(dek, salt=None, info=b"myfinance/v1/table|" + table.encode("utf-8")))
            self._ciphers[table] = cipher
        return cipher

    def _aad(self, table: str, column: str) -> bytes:
        return b"myfinance/v1/cell|" + self.user_id.bytes + b"|" + table.encode() + b"|" + column.encode()

    def seal(self, table: str, column: str, plaintext: bytes) -> bytes:
        nonce = os.urandom(NONCE_LEN)
        return FORMAT_V1 + nonce + self._cipher(table).encrypt(nonce, plaintext, self._aad(table, column))

    def open(self, table: str, column: str, blob: bytes) -> bytes:
        blob = bytes(blob)
        if len(blob) < 1 + NONCE_LEN + 16 or blob[:1] != FORMAT_V1:
            raise DecryptionError("not a recognised ciphertext")
        try:
            return self._cipher(table).decrypt(
                blob[1 : 1 + NONCE_LEN], blob[1 + NONCE_LEN :], self._aad(table, column)
            )
        except InvalidTag as exc:
            raise DecryptionError("authentication failed (wrong key, or not this user/table/column)") from exc

    def __repr__(self) -> str:  # pragma: no cover - never print key material
        return f"<KeyRing user={self.user_id} {'live' if not self.expired() else 'expired'}>"


# --- Which ring the column types use -----------------------------------------------

_ACTIVE: contextvars.ContextVar[KeyRing | None] = contextvars.ContextVar("myfinance_keyring", default=None)


@contextmanager
def activated(ring: KeyRing | None):
    """Make `ring` the one the encrypted column types use, for this block only.

    The session does this around every operation it performs (scoping.KeyedSession),
    so the ring in force is always the one belonging to the session that is
    running the statement - never a leftover from another request or user. Outside
    such a block the column types find no ring and refuse.
    """
    token = _ACTIVE.set(ring)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def active_keyring() -> KeyRing:
    ring = _ACTIVE.get()
    if ring is None:
        raise KeysUnavailable(
            "an encrypted column was read or written by a session that holds no user key "
            "(open it with scoping.open_session(user_id, keyring))"
        )
    return ring
