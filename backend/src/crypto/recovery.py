"""The recovery code.

Why it exists: the data key is wrapped under (KEK, the user's `sub`). If the
`sub` changes - the identity provider is replaced, or an account is re-linked -
the next sign-in is a *different person* as far as this system can tell: a new,
empty user with a fresh key, and the old data can no longer be unlocked. The
recovery code is a second, independent way to unwrap the DEK, held only by the
user, so the old data can be re-attached to the new identity.

Format. `MF1-` and 50 characters of Crockford base32 in groups of five:

    <id: 16 chars = 80 random bits><secret: 32 chars = 160 random bits><check: 2 chars>

The `id` is stored in the clear (`users.recovery_id`, unique) and is how the old
account is found without scanning anyone. The `secret` is never stored. The check
characters are a typo detector only: the first 10 bits of SHA-256 over the rest.
Ambiguous letters are tolerated on input (I and L read as 1, O as 0, U is not in
the alphabet) and case and separators are ignored.

Wrapping. scrypt(secret, per-code salt) gives 64 bytes; HKDF splits that into a
wrapping key for the DEK (AES-256-GCM, AAD = user id) and a *proof*. The database
keeps SHA-256(proof) as `recovery_verifier`, so it can decide for itself whether
a presented code is right before it moves an account (rls.py), without being able
to recover the code or the key from what it holds. The code is long and random,
so the slow KDF is a second line of defence, not the only one.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from ..config import settings
from .core import CryptoError, KEY_LEN, aead_open, aead_seal, hkdf

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_ALPHABET)}
_DECODE.update({"I": 1, "L": 1, "O": 0})

PREFIX = "MF1"
ID_BYTES = 10  # 16 characters
SECRET_BYTES = 20  # 32 characters
SALT_BYTES = 16


class RecoveryCodeError(CryptoError):
    """The text is not a well-formed recovery code (wrong length, bad characters,
    failed check). Says nothing about whether any account has such a code."""


@dataclass(frozen=True)
class ParsedCode:
    recovery_id: str  # 16 uppercase Crockford characters
    secret: bytes


@dataclass(frozen=True)
class Material:
    """What gets stored for a freshly made code, plus the code itself - which is
    shown to the user once and then forgotten."""

    code: str
    recovery_id: str
    salt: bytes
    kdf: str
    wrapped_dek: bytes
    verifier: bytes


def _b32(data: bytes) -> str:
    bits = int.from_bytes(data, "big")
    n = len(data) * 8 // 5
    return "".join(_ALPHABET[(bits >> (5 * (n - 1 - i))) & 31] for i in range(n))


def _unb32(text: str) -> bytes:
    bits = 0
    for ch in text:
        bits = (bits << 5) | _DECODE[ch]
    return bits.to_bytes(len(text) * 5 // 8, "big")


def _check(body: str) -> str:
    digest = hashlib.sha256(b"myfinance/v1/recovery-check|" + body.encode("ascii")).digest()
    value = int.from_bytes(digest[:2], "big") >> 6  # 10 bits
    return _ALPHABET[value >> 5] + _ALPHABET[value & 31]


def format_code(recovery_id: str, secret: bytes) -> str:
    body = recovery_id + _b32(secret)
    full = body + _check(body)
    return PREFIX + "-" + "-".join(full[i : i + 5] for i in range(0, len(full), 5))


def parse(code: str) -> ParsedCode:
    text = re.sub(r"[\s\-_]", "", (code or "")).upper()
    if text.startswith(PREFIX):
        text = text[len(PREFIX) :]
    expected = 16 + 32 + 2
    if len(text) != expected or any(ch not in _DECODE for ch in text):
        raise RecoveryCodeError("that is not a recovery code (check its length and characters)")
    text = "".join(_ALPHABET[_DECODE[ch]] for ch in text)  # canonical spelling
    body, check = text[:-2], text[-2:]
    if not hmac.compare_digest(_check(body), check):
        raise RecoveryCodeError("that recovery code has a typo (its check characters do not match)")
    return ParsedCode(recovery_id=body[:16], secret=_unb32(body[16:]))


# --- derivation ---------------------------------------------------------------


def kdf_descriptor(n: int | None = None) -> str:
    return f"scrypt:n={n or settings.recovery_scrypt_n},r=8,p=1"


def _kdf_params(descriptor: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"scrypt:n=(\d+),r=(\d+),p=(\d+)", descriptor or "")
    if not m:
        raise RecoveryCodeError("unknown recovery key-derivation scheme")
    n, r, p = (int(g) for g in m.groups())
    # A stored descriptor is data; do not let a corrupted one ask for gigabytes.
    if n < 2**10 or n > 2**20 or n & (n - 1) or r > 16 or p > 4:
        raise RecoveryCodeError("unacceptable recovery key-derivation parameters")
    return n, r, p


def derive(secret: bytes, salt: bytes, descriptor: str) -> tuple[bytes, bytes]:
    """(wrapping key, proof) for a code's secret half. Slow on purpose."""
    n, r, p = _kdf_params(descriptor)
    # maxmem is raised well past OpenSSL's 32 MiB default: 128*n*r bytes are needed.
    out = Scrypt(salt=salt, length=64, n=n, r=r, p=p).derive(secret)
    return (
        hkdf(out, salt=None, info=b"myfinance/v1/recovery/wrap"),
        hkdf(out, salt=None, info=b"myfinance/v1/recovery/proof"),
    )


def verifier_of(proof: bytes) -> bytes:
    return hashlib.sha256(proof).digest()


def _aad(user_id: uuid.UUID) -> bytes:
    return b"myfinance/v1/recovery|" + user_id.bytes


def create(user_id: uuid.UUID, dek: bytes) -> Material:
    recovery_id = _b32(os.urandom(ID_BYTES))
    secret = os.urandom(SECRET_BYTES)
    salt = os.urandom(SALT_BYTES)
    descriptor = kdf_descriptor()
    wrap_key, proof = derive(secret, salt, descriptor)
    return Material(
        code=format_code(recovery_id, secret),
        recovery_id=recovery_id,
        salt=salt,
        kdf=descriptor,
        wrapped_dek=aead_seal(wrap_key, dek, _aad(user_id)),
        verifier=verifier_of(proof),
    )


def unwrap(user_id: uuid.UUID, wrapped: bytes, wrap_key: bytes) -> bytes:
    return aead_open(wrap_key, bytes(wrapped), _aad(user_id))


def wrap(user_id: uuid.UUID, dek: bytes, wrap_key: bytes) -> bytes:
    if len(dek) != KEY_LEN:
        raise CryptoError("a DEK is 32 bytes")
    return aead_seal(wrap_key, dek, _aad(user_id))
