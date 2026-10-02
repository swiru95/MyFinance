"""Settings schemas."""
from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import TIMEZONES


class FeatureFlags(BaseModel):
    """Which advanced features this wallet has switched on.

    Base features (Dashboard, Income, Expenses, Settings) are always on and
    have no flag. `fire` needs `portfolio` - FI is computed from assets - so
    that dependency is enforced right here rather than trusted to callers:
    whatever combination comes in, `fire` can never end up true while
    `portfolio` is false.
    """

    portfolio: bool = False
    fire: bool = False
    tax: bool = False
    insights: bool = False

    @model_validator(mode="after")
    def _fire_needs_portfolio(self) -> "FeatureFlags":
        if not self.portfolio:
            self.fire = False
        return self


class SettingsIn(BaseModel):
    base_currency: str = Field(..., pattern="^(PLN|EUR|USD|CHF)$")
    timezone: str | None = None
    features: FeatureFlags | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, v: str | None) -> str | None:
        if v is not None and v not in TIMEZONES:
            raise ValueError(f"timezone must be one of: {', '.join(TIMEZONES)}")
        return v


class TermsAcceptIn(BaseModel):
    """Body of POST /api/settings/terms/accept - the version the client is
    accepting, checked against config.TERMS_VERSION server-side so an old tab
    or a raced release can't record acceptance of the wrong text."""

    version: int


class BirthYearIn(BaseModel):
    """Body of PUT /api/settings/birth-year. `null` clears it. Optional, and only
    the year: it is for the age analysis the insights will use, and it is stored
    encrypted under the user's own key like every other personal figure."""

    birth_year: int | None = Field(None, ge=1900, le=2100)

    @field_validator("birth_year")
    @classmethod
    def _plausible(cls, v: int | None) -> int | None:
        from datetime import date

        if v is not None and v > date.today().year:
            raise ValueError("birth_year cannot be in the future")
        return v
