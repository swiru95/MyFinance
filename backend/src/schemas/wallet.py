"""The wallet file: a versioned, human-readable JSON description of a wallet's
*setup*, and the shapes the import preview answers with.

Everything here is deliberately strict. A file is validated as a whole before
anything is written (services/wallet_io.py), unknown fields are rejected rather
than ignored (a typo must not silently drop a setting), and the item counts are
capped. Monetary amounts are strings, so a decimal keeps its full precision on
the way through JSON; rates and fractions are plain numbers.

The accepted shapes reuse the application's own schemas (AssetIn, ExpenseIn's
rules, IncomeSourceIn, FireSettings) wherever they exist, so a file can never
make a row the normal forms would have refused.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from ..config import TIMEZONES
from .asset import AssetIn
from .fire import FireSettings
from .income import PARAM_MODELS, IncomeSourceIn
from .settings import FeatureFlags

FORMAT = "myfinance-wallet"
VERSION = 1

# Limits. The size cap is enforced on the raw body before it is parsed
# (routes/wallet.py); the counts bound what one file can write.
MAX_FILE_BYTES = 1_000_000
MAX_ASSETS = 200
MAX_INCOME_SOURCES = 50
MAX_EXPENSES = 300

_AMOUNT_RE = re.compile(r"^-?[0-9]{1,13}(\.[0-9]{1,6})?$")
_PROFILES = {"", "safe", "moderate", "risky", "illiquid"}
_KINDS = {"currency", "gold", "metal", "crypto", "interest"}

# Keys of an income source's `params` that are money (exported as strings). The
# rest of the params are rates, shares, switches and enumerations.
INCOME_MONEY_PARAMS = frozenset(
    {"gross_monthly", "invoice_monthly", "net_monthly", "rate", "costs_monthly", "custom_base"}
)
# The same for the FIRE inputs.
FIRE_MONEY_FIELDS = frozenset(
    {"barista_income_monthly", "zus_pension_monthly", "monthly_spend_override"}
)


def _no_controls(v: str) -> str:
    if any(ord(c) < 32 and c not in "\n\t" for c in v):
        raise ValueError("control characters are not allowed")
    return v


Name = Annotated[
    str, StringConstraints(min_length=1, max_length=120), AfterValidator(_no_controls)
]
ShortText = Annotated[str, StringConstraints(max_length=60), AfterValidator(_no_controls)]
Notes = Annotated[str, StringConstraints(max_length=500), AfterValidator(_no_controls)]
Currency = Annotated[str, StringConstraints(pattern="^(PLN|EUR|USD|CHF)$")]


def parse_amount(value: object, *, places: int, field: str) -> Decimal:
    """A money string -> Decimal, with the column's own scale as the limit."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field}: an amount must be a string such as \"120.50\"")
    text = value if isinstance(value, str) else repr(value)
    if not _AMOUNT_RE.match(text):
        raise ValueError(f"{field}: not a plain decimal amount")
    try:
        d = Decimal(text)
    except InvalidOperation:  # pragma: no cover - the regex already says it parses
        raise ValueError(f"{field}: not a number") from None
    if d != d.quantize(Decimal(1).scaleb(-places)):
        raise ValueError(f"{field}: at most {places} decimal places")
    return d


def fmt_amount(value: object) -> str:
    """Decimal text without an exponent or trailing zeros."""
    d = Decimal(str(value)).normalize()
    text = format(d, "f")
    return "0" if text in ("-0", "") else text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WalletFeatures(FeatureFlags):
    model_config = ConfigDict(extra="forbid")


class WalletFire(FireSettings):
    """FIRE inputs. Money fields may be strings; FireSettings coerces them."""

    model_config = ConfigDict(extra="forbid")

    @field_validator(*FIRE_MONEY_FIELDS, mode="before")
    @classmethod
    def _money_strings(cls, v, info):
        if v is None:
            return v
        return float(parse_amount(v, places=2, field=info.field_name))


class WalletSettings(_Strict):
    base_currency: Currency
    timezone: str | None = None
    features: WalletFeatures | None = None
    fire: WalletFire | None = None
    birth_year: int | None = Field(None, ge=1900, le=2100)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, v):
        if v is not None and v not in TIMEZONES:
            raise ValueError(f"timezone must be one of: {', '.join(TIMEZONES)}")
        return v

    @field_validator("birth_year")
    @classmethod
    def _not_future(cls, v):
        if v is not None and v > date.today().year:
            raise ValueError("birth_year cannot be in the future")
        return v


class WalletAsset(_Strict):
    name: Name
    kind: str
    category: ShortText = ""
    units: ShortText = ""
    interest_basis: str = Field("", pattern="^(|late|capital)$")
    profile: str = ""
    icon: Annotated[str, StringConstraints(max_length=16)] = ""
    wrapper: str = ""
    # The currency the amount is in (a currency asset's own currency; for gold,
    # metals and crypto it is the position's nominal currency and unused).
    currency: Currency = "PLN"
    # Latest holding: grams / coin quantity / currency amount / principal.
    amount: str
    # What it is worth now, and what you have paid in over its life, both in
    # settings.base_currency. `contributed` is null when unknown.
    value: str
    contributed: str | None = None
    # Only for kind "interest": the day the principal began to accrue.
    accrues_from: date | None = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in _KINDS:
            raise ValueError(f"kind must be one of: {', '.join(sorted(_KINDS))}")
        return v

    @field_validator("profile")
    @classmethod
    def _profile(cls, v):
        if v not in _PROFILES:
            raise ValueError("profile must be one of: safe, moderate, risky, illiquid, or empty")
        return v

    @field_validator("amount")
    @classmethod
    def _amount(cls, v):
        if parse_amount(v, places=6, field="amount") < 0:
            raise ValueError("amount cannot be negative")
        return v

    @field_validator("value", "contributed")
    @classmethod
    def _money(cls, v, info):
        if v is None:
            return v
        if parse_amount(v, places=4, field=info.field_name) < 0:
            raise ValueError(f"{info.field_name} cannot be negative")
        return v

    @model_validator(mode="after")
    def _like_an_asset(self):
        # Wrapper / crypto-metal units rules are the asset form's own.
        AssetIn(
            name=self.name, kind=self.kind, category=self.category,
            interest_basis=self.interest_basis, profile=self.profile,
            icon=self.icon, units=self.units, wrapper=self.wrapper,
        )
        if self.accrues_from is not None and self.kind != "interest":
            raise ValueError("accrues_from only applies to kind 'interest'")
        return self

    @property
    def amount_d(self) -> Decimal:
        return Decimal(self.amount)

    @property
    def value_d(self) -> Decimal:
        return Decimal(self.value)

    @property
    def contributed_d(self) -> Decimal | None:
        return None if self.contributed is None else Decimal(self.contributed)


class WalletIncomeSource(IncomeSourceIn):
    """An income source. Same rules as the Income form; money params are strings."""

    model_config = ConfigDict(extra="forbid")

    name: Name  # type: ignore[assignment]
    notes: Notes = ""  # type: ignore[assignment]

    @model_validator(mode="before")
    @classmethod
    def _params_shape(cls, data):
        if not isinstance(data, dict):
            return data
        params = data.get("params")
        kind = data.get("kind")
        if isinstance(params, dict) and kind in PARAM_MODELS:
            allowed = set(PARAM_MODELS[kind].model_fields)
            unknown = sorted(set(params) - allowed)
            if unknown:
                raise ValueError(f"unknown params for kind={kind}: {', '.join(unknown)}")
            fixed = dict(params)
            for key in INCOME_MONEY_PARAMS & set(fixed):
                if fixed[key] is not None:
                    fixed[key] = float(parse_amount(fixed[key], places=2, field=f"params.{key}"))
            data = {**data, "params": fixed}
        return data


class WalletExpense(_Strict):
    name: Name
    amount: str
    currency: Currency = "PLN"
    period: str = Field("monthly", pattern="^(monthly|quarterly|yearly)$")
    category: ShortText = ""
    starts_on: date
    ends_on: date | None = None
    notes: Notes = ""

    @field_validator("amount")
    @classmethod
    def _amount(cls, v):
        if parse_amount(v, places=2, field="amount") <= 0:
            raise ValueError("amount must be greater than zero")
        return v

    @model_validator(mode="after")
    def _dates(self):
        if self.ends_on is not None and self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self

    @property
    def amount_d(self) -> Decimal:
        return Decimal(self.amount)


class WalletFile(_Strict):
    format: Literal["myfinance-wallet"]
    version: Literal[1]
    exported_at: str | None = Field(None, max_length=40)
    settings: WalletSettings
    assets: list[WalletAsset] = Field(default_factory=list, max_length=MAX_ASSETS)
    income_sources: list[WalletIncomeSource] = Field(
        default_factory=list, max_length=MAX_INCOME_SOURCES
    )
    expenses: list[WalletExpense] = Field(default_factory=list, max_length=MAX_EXPENSES)


# --- Import preview / result --------------------------------------------------


class PlanItem(BaseModel):
    section: Literal["asset", "income_source", "expense", "setting"]
    name: str
    # create: a new row. fill: an opening position on one of your existing
    # assets that has no balance yet. skip / keep: nothing is written, because
    # something of yours is already there.
    action: Literal["create", "fill", "skip", "keep"]
    # Machine-readable, for the UI to word: new | default_type | already_has_balance |
    # already_exists | already_set | converted | ...
    reason: str = "new"
    # The existing thing involved (a matched asset's name, a setting's current value).
    existing: str | None = None
    # For a setting: the value in the file.
    incoming: str | None = None


class PlanCounts(BaseModel):
    create: int = 0
    fill: int = 0
    skip: int = 0
    keep: int = 0


class PlanWarning(BaseModel):
    # e.g. "base_currency_differs" with args [file base, your base]: the file's
    # paid-in totals were converted at today's rate.
    code: str
    args: list[str] = []


class ImportPlanOut(BaseModel):
    version: int = VERSION
    # False for a preview, True once the plan was written.
    applied: bool = False
    items: list[PlanItem]
    counts: dict[str, PlanCounts]
    # Things worth saying that are not a per-item conflict (e.g. a rate conversion).
    warnings: list[PlanWarning] = []
    # Rows that would be / were written (assets get one or two positions each).
    writes: int = 0
