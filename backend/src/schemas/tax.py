"""Tax preview request shapes.

These mirror tax/pl's own option dataclasses field-for-field so a request
body maps onto UopOptions/B2bOptions with no translation layer, and add the
bounds a UI slider would already enforce but a JSON body cannot be trusted to
have kept. `to_options()` on each pulls out exactly the engine's fields, so a
subclass (schemas/income.py) can add its own fields without them leaking
into the dataclass constructor call.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..tax.pl.b2b import B2bOptions
from ..tax.pl.uop import UopOptions

_UOP_FIELDS = (
    "kup",
    "creative_share",
    "pit2",
    "young_relief",
    "ppk_employee",
    "ppk_employee_extra",
    "ppk_employer",
    "ppk_employer_extra",
    "accident_rate",
)
_B2B_FIELDS = (
    "tax_form",
    "ryczalt_rate",
    "zus_stage",
    "custom_base",
    "sickness",
    "vat",
    "vat_rate",
    "costs_vat_rate",
)


class UopOptionsIn(BaseModel):
    kup: str = Field("standard", pattern="^(standard|commuting)$")
    creative_share: float = Field(0.0, ge=0, le=1)
    pit2: bool = True
    young_relief: bool = False
    ppk_employee: float = Field(0.02, ge=0, le=0.02)
    ppk_employee_extra: float = Field(0.0, ge=0, le=0.02)
    ppk_employer: float = Field(0.015, ge=0, le=0.015)
    ppk_employer_extra: float = Field(0.0, ge=0, le=0.025)
    accident_rate: float = Field(0.0167, ge=0, le=1)

    def to_options(self) -> UopOptions:
        return UopOptions(**{f: getattr(self, f) for f in _UOP_FIELDS})


class B2bOptionsIn(BaseModel):
    tax_form: str = Field("liniowy", pattern="^(skala|liniowy|ryczalt)$")
    ryczalt_rate: float = Field(0.12, ge=0, le=1)
    zus_stage: str = Field("full", pattern="^(start|preferential|maly_zus_plus|full)$")
    custom_base: float | None = Field(None, ge=0)
    sickness: bool = False
    vat: str = Field("standard", pattern="^(standard|exempt|reverse_charge)$")
    vat_rate: float = Field(0.23, ge=0, le=1)
    costs_vat_rate: float = Field(0.23, ge=0, le=1)

    @model_validator(mode="after")
    def _check_custom_base(self):
        if self.zus_stage == "maly_zus_plus" and self.custom_base is None:
            raise ValueError("custom_base is required when zus_stage is maly_zus_plus")
        return self

    def to_options(self) -> B2bOptions:
        return B2bOptions(**{f: getattr(self, f) for f in _B2B_FIELDS})


def _twelve(monthly: float | None, by_month: list[float] | None, field: str) -> list[float]:
    """Expand a `<field>_monthly` / `<field>_by_month` pair into 12 entries."""
    if by_month is not None:
        if len(by_month) != 12:
            raise ValueError(f"{field}_by_month must have exactly 12 entries")
        if any(v < 0 for v in by_month):
            raise ValueError(f"{field}_by_month values must be >= 0")
        return list(by_month)
    if monthly is not None:
        return [monthly] * 12
    raise ValueError(f"one of {field}_monthly or {field}_by_month is required")


class UopPreviewIn(BaseModel):
    year: int
    gross_monthly: float | None = Field(None, ge=0)
    gross_by_month: list[float] | None = None
    options: UopOptionsIn = UopOptionsIn()

    @model_validator(mode="after")
    def _check_shape(self):
        _twelve(self.gross_monthly, self.gross_by_month, "gross")
        return self

    def gross_list(self) -> list[float]:
        return _twelve(self.gross_monthly, self.gross_by_month, "gross")


class B2bPreviewIn(BaseModel):
    year: int
    revenue_monthly: float | None = Field(None, ge=0)
    revenue_by_month: list[float] | None = None
    costs_monthly: float | None = Field(None, ge=0)
    costs_by_month: list[float] | None = None
    options: B2bOptionsIn = B2bOptionsIn()

    @model_validator(mode="after")
    def _check_shape(self):
        _twelve(self.revenue_monthly, self.revenue_by_month, "revenue")
        if self.costs_monthly is not None or self.costs_by_month is not None:
            _twelve(self.costs_monthly, self.costs_by_month, "costs")
        return self

    def revenue_list(self) -> list[float]:
        return _twelve(self.revenue_monthly, self.revenue_by_month, "revenue")

    def costs_list(self) -> list[float]:
        if self.costs_monthly is None and self.costs_by_month is None:
            return [0.0] * 12
        return _twelve(self.costs_monthly, self.costs_by_month, "costs")


class ComparePreviewIn(BaseModel):
    year: int
    uop_gross_monthly: float = Field(..., ge=0)
    uop_options: UopOptionsIn = UopOptionsIn()
    b2b_revenue_monthly: float = Field(..., ge=0)
    b2b_costs_monthly: float = Field(0.0, ge=0)
    b2b_options: B2bOptionsIn = B2bOptionsIn()
    paid_leave_days: int = Field(26, ge=0, le=366)
    # None -> the statutory working-time calendar's total for `year`
    # (tax/pl/calendar.py), not a fixed guess.
    working_days: int | None = Field(None, gt=0, le=366)
    b2b_billed_per_day: bool = True


class ReverseIn(BaseModel):
    year: int
    target_net_monthly: float = Field(..., ge=0)
    uop_options: UopOptionsIn = UopOptionsIn()
    b2b_options: B2bOptionsIn = B2bOptionsIn()
    costs_monthly: float = Field(0.0, ge=0)
