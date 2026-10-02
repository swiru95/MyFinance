"""Income source model.

An income source is a recurring expense pointed the other way: `params` hold
the default monthly figures, they apply in every month between `starts_on`
and `ends_on`, and an `IncomeEntry` overrides exactly one month (a bonus, an
unpaid month, a different invoice) without touching the source's own
default. Shape of `params` depends on `kind` - see schemas/income.py.
"""
from datetime import date, datetime, timezone

from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..crypto.fields import EncDate, EncDecimal, EncJSON, EncStr
from ..database import Base
from .types import UtcDateTime
from .user import Owned


class IncomeSource(Owned, Base):
    __tablename__ = "income_sources"
    __table_args__ = (
        # Target of income_entries' composite foreign key; see IncomeEntry.
        UniqueConstraint("user_id", "id", name="uq_income_sources_user_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(EncStr(), nullable=False)
    # kind: uop | b2b | other
    kind: Mapped[str] = mapped_column(EncStr(), nullable=False)
    currency: Mapped[str] = mapped_column(EncStr(), nullable=False, default="PLN")
    params: Mapped[dict] = mapped_column(EncJSON(), nullable=False, default=dict)
    starts_on: Mapped[date] = mapped_column(EncDate(), nullable=False)
    # NULL => still running.
    ends_on: Mapped[date | None] = mapped_column(EncDate(), nullable=True)
    notes: Mapped[str] = mapped_column(EncStr(), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IncomeSource {self.name} {self.kind}>"


class IncomeEntry(Owned, Base):
    """One month's actual figures for a source, overriding its param default.

    Deleting a source deletes its entries explicitly in the route - SQLite
    does not enforce FK cascades by default.
    """

    __tablename__ = "income_entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source_id", "month", name="uq_income_entry_user_source_month"
        ),
        # An entry cannot belong to another user's source - see
        # Position.__table_args__ for why this is a composite key.
        ForeignKeyConstraint(
            ["user_id", "source_id"],
            ["income_sources.user_id", "income_sources.id"],
            name="fk_income_entries_user_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(nullable=False, index=True)
    # Calendar month as "YYYY-MM".
    month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    # uop: gross; b2b: invoice net revenue; other: net.
    amount: Mapped[float] = mapped_column(EncDecimal(20, 2), nullable=False)
    # Days/hours actually worked this month, for a day/hour-billed b2b
    # source - reference only; `amount` above is always the frozen revenue
    # figure (rate x units, resolved once at write time by the route).
    units: Mapped[float | None] = mapped_column(EncDecimal(10, 2), nullable=True)
    # b2b net business costs for the month.
    costs: Mapped[float] = mapped_column(EncDecimal(20, 2), nullable=False, default=0)
    # The real net from a payslip/bank statement, when known; wins over
    # whatever the tax engine would estimate because it is not an estimate.
    override_net: Mapped[float | None] = mapped_column(EncDecimal(20, 2), nullable=True)
    notes: Mapped[str] = mapped_column(EncStr(), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IncomeEntry source={self.source_id} {self.month} {self.amount}>"
