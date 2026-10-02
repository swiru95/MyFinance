"""Key-check values: one per KEK version, written by the schema job.

Each is a fixed message sealed under that KEK version (crypto/core.make_key_check).
Startup and the schema job open it with the configured KEK before doing anything
else, so a Secret that holds the wrong key - a typo, last month's value, another
cluster's - is reported by name instead of surfacing as every user failing to
unlock, or worse as new users being wrapped under a key the database has never seen.

Not secret and not user data: no user_id, no row-level security. The runtime role
may read it and nothing else.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .types import UtcDateTime


class KeyCheck(Base):
    __tablename__ = "key_check"

    kek_version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    check_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
