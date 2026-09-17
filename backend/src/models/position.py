"""Position model - each row is a timestamped snapshot of an asset."""
from datetime import datetime, timezone
from sqlalchemy import Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    # For currency assets: amount in `currency`.
    # For gold: grams. For crypto: coin quantity.
    amount: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    # Only meaningful for currency-kind assets.
    # Snapshot of value in the base currency at the time of the update.
    value_in_base: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False, default=0.0)
    # Price used for the snapshot (per gram / per coin / fx rate).
    price_used: Mapped[float] = mapped_column(Numeric(20, 6), nullable=False, default=0.0)
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
