"""How a person is recognised without the database knowing who they are.

`users.subject_hash` = HMAC-SHA256(pepper, issuer + "|" + sub), hex-encoded.

The HMAC key (the "pepper") lives in the environment, not the database, so a
copy of the database alone cannot be used to confirm that a given person has an
account - unlike a bare hash of a guessable value. The issuer is part of the
input because `sub` is only unique *within* an issuer.

The raw `sub` is used for this one computation and then dropped. It is never
stored, returned, or logged - and neither are the name and email claims, which
this application never reads at all.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid

from .config import settings

# The fixed user that every request belongs to while authentication is off
# (local development). A constant id so the same database keeps its owner
# across restarts; the hash is derived from a constant, not from a pepper,
# because there may not be one.
LOCAL_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
_LOCAL_HASH_KEY = b"myfinance-local-user"


class PepperMissing(RuntimeError):
    """Authentication is on but MYFINANCE_SUBJECT_PEPPER is not set."""


def subject_hash(issuer: str, sub: str, pepper: str | None = None) -> str:
    pepper = settings.subject_pepper if pepper is None else pepper
    if not pepper:
        raise PepperMissing("MYFINANCE_SUBJECT_PEPPER must be set when authentication is enabled")
    if not issuer or not sub:
        raise ValueError("issuer and sub are both required")
    return hmac.new(
        pepper.encode("utf-8"), f"{issuer}|{sub}".encode("utf-8"), hashlib.sha256
    ).hexdigest()


def local_subject_hash() -> str:
    return hmac.new(_LOCAL_HASH_KEY, b"local|local", hashlib.sha256).hexdigest()
