"""Per-month budget record.

One row per calendar month holding what you actually earned and spent. The
*committed* figure for a month is never stored - it is derived from the
recurring expense definitions, so editing an expense retroactively corrects
every month it applies to.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .user import Owned


class MonthlyRecord(Owned, Base):
    __tablename__ = "monthly_records"
    # One record per month *per user*. Its index (user_id leading) serves every
    # lookup, since all of them are scoped to a user, so `month` carries no
    # index of its own.
    __table_args__ = (UniqueConstraint("user_id", "month", name="uq_monthly_user_month"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Calendar month as "YYYY-MM".
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    income: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    actual_spent: Mapped[float] = mapped_column(
        Numeric(20, 2), nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The "month checklist" breakdown behind actual_spent (WP-M): which
    # commitments were paid, at what amount, plus whatever else was spent.
    # JSON list of {"expense_id", "name", "amount", "currency", "paid"} - the
    # expense's own currency, not necessarily this record's. NULL on both
    # this and other_spent means a legacy "one total" record, which keeps
    # reading and writing exactly as before actual_spent became derived.
    commitments_paid: Mapped[str | None] = mapped_column(Text, nullable=True)
    other_spent: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MonthlyRecord {self.month} in={self.income} out={self.actual_spent}>"
