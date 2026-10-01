"""Position model - each row is a timestamped snapshot of an asset."""
from datetime import date, datetime, timezone
from sqlalchemy import Integer, String, Numeric, Date, ForeignKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .types import UtcDateTime
from .user import Owned


class Position(Owned, Base):
    __tablename__ = "positions"
    __table_args__ = (
        # (user_id, asset_id), not asset_id alone: the database itself refuses
        # a position that points at another user's asset, whatever the
        # application or row-level security would have let through. (Referential
        # integrity checks bypass RLS, so a plain asset_id foreign key would
        # accept - and confirm the existence of - any user's asset id.)
        ForeignKeyConstraint(
            ["user_id", "asset_id"], ["assets.user_id", "assets.id"], name="fk_positions_user_asset"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    asset_id: Mapped[int] = mapped_column(nullable=False, index=True)
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
    # Only for kind="interest": the day the principal started accruing. NULL
    # everywhere else.
    accrues_from: Mapped["date | None"] = mapped_column(Date, nullable=True)
    # Money moved into (+) or out of (-) this asset since the previous
    # snapshot, in base currency at this snapshot's prices. NULL means
    # unknown, not zero - a snapshot without a recorded flow says nothing
    # about whether money moved, so it must not be counted as a zero
    # contribution by anything that sums this column (see services/fire.py).
    flow_in_base: Mapped["float | None"] = mapped_column(Numeric(20, 4), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(UtcDateTime, default=lambda: datetime.now(timezone.utc), index=True)
