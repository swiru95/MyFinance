"""Users, and the ownership mixin every data table carries.

A user row holds *no personal data*. It is keyed by an opaque UUID and found
again through `subject_hash`, an HMAC of the identity provider's issuer and
subject under a server-side pepper (see identity.py). Name and email never
reach this table: the browser reads them from its own token. (An address a user
opts in to share for notifications lives in its own table, under its own key -
models/contact.py.)

It also holds the user's key material: their data key wrapped under the KEK and
their own token claim, and a second copy wrapped under their recovery code. None
of it opens anything without those secrets (see crypto/).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..crypto.fields import EncInt
from ..database import Base
from .types import UtcDateTime


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Hex HMAC-SHA256: 64 characters. Unique, because it is how a returning
    # user is recognised.
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # The terms-of-use version this user has accepted (config.TERMS_VERSION is
    # the current one) and when. NULL until they accept.
    terms_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    terms_accepted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # --- Key material (src/crypto). All of it is useless without the KEK and,
    # for the first three, the user's own token claim; none of it is a secret
    # that unlocks anything by itself. NULL until the user's first request
    # after the encryption migration (services/users.py creates them then).
    #
    # `wrapped_dek`: the user's random data key, AES-GCM-wrapped under a key
    # derived from (KEK, key_salt, the user's claim). `kek_version` says which KEK.
    key_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    kek_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Recovery code (crypto/recovery.py). The code itself is never stored.
    # `recovery_id` is the random lookup half of the code, so the old account is
    # found without scanning anyone; `recovery_wrapped_dek` is the DEK wrapped
    # again under a key made from the secret half with scrypt; `recovery_verifier`
    # is a hash of a value derived from the same scrypt output, which lets the
    # database itself check a presented code before it moves an account.
    recovery_id: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)
    recovery_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_kdf: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recovery_wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_verifier: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    recovery_created_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # Set once the user has typed the code back (routes/recovery.py: confirm).
    recovery_confirmed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    # Wrong codes submitted *by this account* and the lock they earned - kept
    # here, not in memory, so every replica sees the same count.
    recovery_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    recovery_locked_until: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    # Optional, for the age analysis planned for the insights. Encrypted under
    # the user's own key like every other personal figure; deferred so that
    # loading the user row (the terms check, a system session) never needs it.
    birth_year: Mapped[int | None] = mapped_column(EncInt(), nullable=True, deferred=True)

    def __repr__(self) -> str:  # pragma: no cover
        # The id only. subject_hash is not secret as such, but there is no
        # reason for it to turn up in a traceback either.
        return f"<User {self.id}>"


class Owned:
    """Mixin for every table whose rows belong to one user.

    Marks the table for the automatic scoping in scoping.py: a session opened
    for a user can neither read nor write another user's rows of any class
    that inherits this. `user_id` is NOT NULL with a foreign key, so a row can
    never exist without an owner.
    """

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
