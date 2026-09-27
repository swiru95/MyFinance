"""FIRE settings.

Stored as one JSON blob under the `settings` table's "fire" key rather than
its own table - it is one person's plan, read and written as a whole, never
queried by field.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class FireSettings(BaseModel):
    # None until the person tells us - current_age has no honest default, and
    # 0 would silently price a newborn's FIRE plan.
    birth_year: int | None = Field(None, ge=1900)
    target_fi_age: float | None = Field(None, ge=18, le=100)
    retirement_age: float = 65  # statutory: 65 men, 60 women; user picks
    swr: float = Field(0.035, ge=0.02, le=0.06)
    inflation: float = Field(0.035, ge=0, le=0.15)
    real_return_override: float | None = Field(None, ge=-0.05, le=0.15)
    monthly_spend_override: float | None = Field(None, ge=0)
    barista_income_monthly: float = Field(0, ge=0)
    # Net, today's money, from PUE ZUS - not derived, because a projected ZUS
    # pension depends on a whole career history this app does not model.
    zus_pension_monthly: float = Field(0, ge=0)
    include_health_cost: bool = True  # voluntary NFZ while not working
    gain_share: float = Field(0.5, ge=0, le=1)
    emergency_months: float = Field(6, ge=0, le=24)
    lean_factor: float = 0.8
    fat_factor: float = 1.5

    @field_validator("birth_year")
    @classmethod
    def _not_in_the_future(cls, v: int | None) -> int | None:
        if v is not None and v > date.today().year:
            raise ValueError("birth_year cannot be in the future")
        return v
