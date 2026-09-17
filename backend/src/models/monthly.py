"""Per-month budget record.

One row per calendar month holding what you actually earned and spent. The
*committed* figure for a month is never stored - it is derived from the
recurring expense definitions, so editing an expense retroactively corrects
every month it applies to.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Numeric, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class MonthlyRecord(Base):
    __tablename__ = "monthly_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Calendar month as "YYYY-MM".
    month: Mapped[str] = mapped_column(
        String(7), nullable=False, unique=True, index=True
    )
    income: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    actual_spent: Mapped[float] = mapped_column(
        Numeric(20, 2), nullable=False, default=0
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MonthlyRecord {self.month} in={self.income} out={self.actual_spent}>"
