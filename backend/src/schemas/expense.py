"""Expense schemas."""
from datetime import date, datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    model_validator,
)

from ..timeutils import as_utc


class ExpenseIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(..., gt=0)
    currency: str = Field("PLN", pattern="^(PLN|EUR|USD|CHF)$")
    period: str = Field("monthly", pattern="^(monthly|once)$")
    category: str = ""
    starts_on: date
    ends_on: date | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _check_dates(self):
        if self.period == "once":
            # A one-off is due on starts_on; an end date is meaningless.
            self.ends_on = None
        elif self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    amount: float
    currency: str
    period: str
    category: str
    starts_on: date
    ends_on: date | None
    notes: str
    created_at: datetime
    # Computed, not stored:
    amount_in_base: float = 0.0
    base_currency: str = "PLN"
    status: str = "active"  # active | scheduled | ended
    is_indefinite: bool = False

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)


class ExpenseSummary(BaseModel):
    base_currency: str
    monthly_total: float
    active_count: int
    indefinite_count: int
    # One-off payments still ahead of us, soonest first.
    upcoming: list[ExpenseOut]
    # Monthly commitments with an end date within the next 90 days.
    ending_soon: list[ExpenseOut]
    by_category: list[dict]
