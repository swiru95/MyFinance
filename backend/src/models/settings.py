"""Simple key/value settings, one set per user."""
import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .user import Owned


class Setting(Owned, Base):
    __tablename__ = "settings"

    # Part of the primary key rather than a plain indexed column: a key is
    # unique *per user*, and the PK index already serves lookups by user.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), primary_key=True
    )
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
