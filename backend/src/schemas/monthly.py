"""Monthly budget schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..services.budget import MONTH_RE


class MonthlyIn(BaseModel):
    income: float = Field(0, ge=0)
    actual_spent: float = Field(0, ge=0)
    currency: str = Field("PLN", pattern="^(PLN|EUR|USD|CHF)$")
    notes: str = ""


class MonthlyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    income: float
    actual_spent: float
    currency: str
    notes: str
    base_currency: str = "PLN"
    # Everything below is derived, never stored.
    income_in_base: float = 0.0
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
