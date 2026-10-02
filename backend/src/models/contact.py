"""A user's notification address, in its own trust domain.

Everything else a user owns is encrypted under a key only their live token can
unlock. A notification is sent while they are *not* signed in, so the address
cannot live under that key. It is encrypted instead under a server-side contact
key (MYFINANCE_CONTACT_KEY, crypto/contacts.py) that is a separate secret from the
KEK and is not derived from it: whatever is one day allowed to read addresses
(a notifier) is not thereby able to read a single financial value, and the
reverse.

Rows exist only for people who opted in, and the address is erased again when
they opt out or unsubscribe. The address is taken from the token's `email`
claim, and only when the identity provider says `email_verified`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .types import UtcDateTime
from .user import Owned


class UserContact(Owned, Base):
    __tablename__ = "user_contacts"

    # One contact per user, so the owner column is the key (as in settings).
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), primary_key=True)
    # AES-GCM under the contact key, AAD naming the user and the column. NULL
    # once the person has opted out.
    email: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # SHA-256 of the unsubscribe token. The token is not stored: whoever may send
    # mail recomputes it from the contact key (crypto/contacts.unsubscribe_token),
    # the database can only recognise it. `token_version` lets a new one be issued.
    unsubscribe_token_hash: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, unique=True
    )
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserContact {self.user_id} opt_in={self.notify_opt_in}>"
