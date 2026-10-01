"""Users, and the ownership mixin every data table carries.

A user row holds *no personal data*. It is keyed by an opaque UUID and found
again through `subject_hash`, an HMAC of the identity provider's issuer and
subject under a server-side pepper (see identity.py). Name and email never
reach the database: the browser reads them from its own token.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

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
