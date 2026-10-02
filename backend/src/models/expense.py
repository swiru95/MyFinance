"""Recurring expense model.

Each row is a standing commitment (rent, a subscription, a loan installment)
rather than a single logged payment.

- period "monthly":   recurs every month from `starts_on`. `ends_on` is the last
  month it is charged; NULL means it runs indefinitely.
- period "quarterly": recurs every 3 months on the same day as `starts_on`.
  `ends_on` is the last quarter in which it is charged; NULL means forever.
- period "yearly":    recurs annually on the same day as `starts_on`.
  `ends_on` is the last year it is charged; NULL means forever.
- period "once":      a single payment due on `starts_on`. `ends_on` is unused.
"""
from datetime import date, datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column

from ..crypto.fields import EncDate, EncDecimal, EncStr
from ..database import Base
from .types import UtcDateTime
from .user import Owned


class Expense(Owned, Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(EncStr(), nullable=False)
    amount: Mapped[float] = mapped_column(EncDecimal(20, 2), nullable=False)
    currency: Mapped[str] = mapped_column(EncStr(), nullable=False, default="PLN")
    # period: monthly | once
    period: Mapped[str] = mapped_column(EncStr(), nullable=False, default="monthly")
    category: Mapped[str] = mapped_column(EncStr(), nullable=False, default="")
    starts_on: Mapped[date] = mapped_column(EncDate(), nullable=False)
    # NULL => runs forever (only meaningful for period="monthly").
    ends_on: Mapped[date | None] = mapped_column(EncDate(), nullable=True)
    notes: Mapped[str] = mapped_column(EncStr(), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Expense {self.name} {self.amount}{self.currency} {self.period}>"
