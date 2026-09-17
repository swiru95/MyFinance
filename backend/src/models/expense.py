"""Recurring expense model.

Each row is a standing commitment (rent, a subscription, a loan installment)
rather than a single logged payment.

- period "monthly": recurs every month from `starts_on`. `ends_on` is the last
  month it is charged; NULL means it runs indefinitely.
- period "once":    a single payment due on `starts_on`. `ends_on` is unused.
"""
from datetime import date, datetime, timezone

from sqlalchemy import String, Numeric, Date, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    # period: monthly | once
    period: Mapped[str] = mapped_column(String(10), nullable=False, default="monthly")
    category: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    starts_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL => runs forever (only meaningful for period="monthly").
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense {self.name} {self.amount}{self.currency} {self.period}>"
