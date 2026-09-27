"""Income source model.

An income source is a recurring expense pointed the other way: `params` hold
the default monthly figures, they apply in every month between `starts_on`
and `ends_on`, and an `IncomeEntry` overrides exactly one month (a bonus, an
unpaid month, a different invoice) without touching the source's own
default. Shape of `params` depends on `kind` - see schemas/income.py.
"""
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class IncomeSource(Base):
    __tablename__ = "income_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # kind: uop | b2b | other
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="PLN")
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL => still running.
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IncomeSource {self.name} {self.kind}>"


class IncomeEntry(Base):
    """One month's actual figures for a source, overriding its param default.

    Deleting a source deletes its entries explicitly in the route - SQLite
    does not enforce FK cascades by default.
    """

    __tablename__ = "income_entries"
    __table_args__ = (
        UniqueConstraint("source_id", "month", name="uq_income_entry_source_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("income_sources.id"), nullable=False, index=True
    )
    # Calendar month as "YYYY-MM".
    month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    # uop: gross; b2b: invoice net revenue; other: net.
    amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    # Days/hours actually worked this month, for a day/hour-billed b2b
    # source - reference only; `amount` above is always the frozen revenue
    # figure (rate x units, resolved once at write time by the route).
    units: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    # b2b net business costs for the month.
    costs: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    # The real net from a payslip/bank statement, when known; wins over
    # whatever the tax engine would estimate because it is not an estimate.
    override_net: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IncomeEntry source={self.source_id} {self.month} {self.amount}>"
