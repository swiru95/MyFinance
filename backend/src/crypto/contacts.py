"""The contact key: a second trust domain, for notification addresses only.

`MYFINANCE_CONTACT_KEY` is 32 random bytes in its own Secret. It is not derived
from, and cannot derive, the KEK or any user's key, and nothing financial is ever
sealed under it; so holding it (as a future notifier would, because it has to
read addresses while nobody is signed in) reveals addresses and nothing else.

Two subkeys come out of it by HKDF: one for the address ciphertext, one for the
unsubscribe tokens. The token is an HMAC of (user, version), so whatever sends
mail can recompute it for any user and build the link, while the database stores
only its SHA-256 - enough to recognise the token, not to forge one.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

from ..config import settings
from .core import CryptoError, KEY_LEN, aead_open, aead_seal, hkdf


class ContactKeyError(CryptoError):
    """The contact key is missing or malformed."""


def _key() -> bytes:
    raw = settings.contact_key.strip()
    if not raw:
        raise ContactKeyError("MYFINANCE_CONTACT_KEY is not set")
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except Exception as exc:
        raise ContactKeyError("MYFINANCE_CONTACT_KEY is not valid base64") from exc
    if len(key) < KEY_LEN:
        raise ContactKeyError(f"MYFINANCE_CONTACT_KEY must decode to at least {KEY_LEN} bytes")
    return key


def validate() -> None:
    _key()


def configured() -> bool:
    try:
        _key()
    except ContactKeyError:
        return False
    return True


def _enc_key() -> bytes:
    return hkdf(_key(), salt=None, info=b"myfinance/v1/contacts/email")


def _mac_key() -> bytes:
    return hkdf(_key(), salt=None, info=b"myfinance/v1/contacts/unsubscribe")


def _aad(user_id: uuid.UUID) -> bytes:
    return b"myfinance/v1/contact|" + user_id.bytes + b"|user_contacts|email"


def seal_email(user_id: uuid.UUID, email: str) -> bytes:
    return aead_seal(_enc_key(), email.encode("utf-8"), _aad(user_id))


def open_email(user_id: uuid.UUID, blob: bytes) -> str:
    return aead_open(_enc_key(), bytes(blob), _aad(user_id)).decode("utf-8")


def unsubscribe_token(user_id: uuid.UUID, version: int) -> str:
    """The token a notifier puts in an e-mail's unsubscribe link."""
    mac = hmac.new(_mac_key(), b"unsubscribe|" + user_id.bytes + b"|%d" % version, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()
