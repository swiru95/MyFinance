"""Monthly budget schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..services.budget import MONTH_RE


class CommitmentInput(BaseModel):
    """One row of the "month checklist": did this recurring expense get
    paid, and for how much - amount is in that expense's own currency."""

    expense_id: int
    amount: float = Field(..., ge=0)
    paid: bool


class MonthlyIn(BaseModel):
    income: float = Field(0, ge=0)
    actual_spent: float = Field(0, ge=0)
    currency: str = Field("PLN", pattern="^(PLN|EUR|USD|CHF)$")
    notes: str = ""
    # When either of these is given, the server derives actual_spent from
    # them instead (see routes/monthly._apply_month_write) - actual_spent
    # above is then only the fallback for the legacy "one total" caller.
    commitments: list[CommitmentInput] | None = None
    other_spent: float | None = Field(None, ge=0)


class MonthlyPatch(BaseModel):
    """Partial update - every field optional, so one page can touch its own
    figure (Expenses: the checklist/notes; Income: income/currency) without
    clobbering the value the other page owns on the same row. A full PUT
    always writes every field and so is unsafe for that split-edit case."""

    income: float | None = Field(None, ge=0)
    actual_spent: float | None = Field(None, ge=0)
    currency: str | None = Field(None, pattern="^(PLN|EUR|USD|CHF)$")
    notes: str | None = None
    commitments: list[CommitmentInput] | None = None
    other_spent: float | None = Field(None, ge=0)


class CommitmentOut(BaseModel):
    """One commitment as shown on the month checklist - GET .../commitments."""

    expense_id: int
    name: str
    category: str
    amount: float
    currency: str
    paid: bool


class MonthlyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    income: float
    actual_spent: float
    currency: str
    notes: str
    base_currency: str = "PLN"
    # The month-checklist breakdown behind actual_spent, in the record's own
    # currency. None/None/False on a legacy "one total" record that has
    # never been saved through the checklist.
    commitments_paid_total: float | None = None
    other_spent: float | None = None
    breakdown: bool = False
    # Everything below is derived, never stored.
    # income_in_base is the typed `income` above converted to base, PLUS
    # every active income source's net for the month - the figure every
    # other derived field (surplus, savings_rate, effective_spent) is built
    # on. income_from_sources_in_base isolates just the source part, and
    # income_sources lists each contributing source for the UI to break down.
    income_in_base: float = 0.0
    income_from_sources_in_base: float = 0.0
    income_sources: list[dict] = []
    actual_in_base: float = 0.0
    committed: float = 0.0
    surplus: float = 0.0
    savings_rate: float | None = None
    variance: float = 0.0
    # Spend read off the portfolio instead of typed in: income minus the change
    # in total value over the month. None when there is no income recorded or no
    # snapshot on one end of the month - see services/budget.effective_spend.
    wallet_start: float | None = None
    wallet_end: float | None = None
    wallet_change: float | None = None
    effective_spent: float | None = None
    by_category: list[dict] = []
    saved: bool = True
    updated_at: datetime | None = None


class TimelinePoint(BaseModel):
    month: str
    committed: float
    income: float | None = None
    actual: float | None = None
    surplus: float | None = None
    effective: float | None = None


class MonthlyAnalytics(BaseModel):
    base_currency: str
    timeline: list[TimelinePoint]
    # Per-category committed spend for each month in the timeline.
    categories: list[str]
    category_series: list[dict]
    avg_income: float | None
    avg_actual: float | None
    avg_effective: float | None
    avg_savings_rate: float | None
    months_recorded: int
    # Months with typed spending; fewer than months_recorded when income
    # comes from sources in months nobody filled in.
    months_with_spend: int = 0
