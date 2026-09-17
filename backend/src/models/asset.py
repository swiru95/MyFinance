"""Asset type model."""
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="currency")
    # kind: currency | gold | crypto - how the position is *valued*, not what the
    # user calls it. `category` is the user-facing class (Cash, Stocks,
    # Retirement, ...) that several differently-named assets can share.
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    icon: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    units: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    # units: e.g. "BTC", "SOL", "g"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset {self.name} ({self.kind})>"
