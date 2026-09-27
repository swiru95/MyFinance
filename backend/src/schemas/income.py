"""Income source schemas: recurring income definitions and the entries that
override one month of them.

`params` is validated per `kind` against the shapes below, then stored back
onto the model as a plain dict with every default filled in - so
services/income.py never has to guess whether an older row is missing a
field a newer version of this schema added.
"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .tax import B2bOptionsIn, UopOptionsIn


class UopIncomeParams(UopOptionsIn):
    gross_monthly: float = Field(..., ge=0)


class B2bIncomeParams(B2bOptionsIn):
    billing: str = Field("monthly", pattern="^(monthly|daily|hourly)$")
    invoice_monthly: float | None = Field(None, ge=0)
    rate: float | None = Field(None, ge=0)
    units_per_month: float | None = Field(None, ge=0)
    costs_monthly: float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def _check_billing_fields(self):
        if self.billing == "monthly" and self.invoice_monthly is None:
            raise ValueError("invoice_monthly is required when billing is monthly")
        if self.billing in ("daily", "hourly") and (
            self.rate is None or self.units_per_month is None
        ):
            raise ValueError(
                "rate and units_per_month are required when billing is daily or hourly"
            )
        return self

    def default_revenue_monthly(self) -> float:
        if self.billing == "monthly":
            return float(self.invoice_monthly or 0.0)
        return float(self.rate or 0.0) * float(self.units_per_month or 0.0)


class OtherIncomeParams(BaseModel):
    # Rental, 800+, anything already net - no tax maths applies.
    net_monthly: float = Field(..., ge=0)


PARAM_MODELS = {"uop": UopIncomeParams, "b2b": B2bIncomeParams, "other": OtherIncomeParams}


class IncomeSourceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    kind: str = Field(..., pattern="^(uop|b2b|other)$")
    currency: str = Field("PLN", pattern="^(PLN|EUR|USD|CHF)$")
    params: dict = Field(default_factory=dict)
    starts_on: date
    ends_on: date | None = None
    notes: str = ""

    @model_validator(mode="after")
    def _validate(self):
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        model_cls = PARAM_MODELS[self.kind]
        try:
            parsed = model_cls.model_validate(self.params)
        except ValidationError as exc:
            raise ValueError(f"invalid params for kind={self.kind}: {exc}") from exc
        # Store back with every default filled in, so a later reader never
        # has to special-case a field this schema added after the row was
        # created.
        self.params = parsed.model_dump()
        return self


class IncomeSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    currency: str
    params: dict
    starts_on: date
    ends_on: date | None
    notes: str
    created_at: datetime
    # Computed, not stored:
    year_summary: dict = {}
    current_month: dict = {}


class IncomeEntryIn(BaseModel):
    amount: float = Field(..., ge=0)
    costs: float = Field(0.0, ge=0)
    override_net: float | None = None
    notes: str = ""


class IncomeEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    amount: float
    costs: float
    override_net: float | None
    notes: str
    updated_at: datetime
