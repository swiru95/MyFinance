"""Asset schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from ..tax.pl.wrappers import WRAPPERS as _WRAPPER_INFO
from ..timeutils import as_utc

# "" = not in any wrapper. Four of the five (ike/ikze/ppk/oipe) are penalised
# before a different age (see services/fire.ACCESS_AGE); oki has no age lock
# at all (see tax/pl/wrappers.py) - the whole reason FIRE math needs to know
# about wrapper at all. Derived from the single wrapper table rather than
# re-listed here so a new wrapper is added in one place.
WRAPPERS = {""} | set(_WRAPPER_INFO)


def _check_wrapper(v: str | None) -> str | None:
    if v is not None and v not in WRAPPERS:
        raise ValueError(f"wrapper must be one of: {', '.join(sorted(WRAPPERS))}")
    return v


class AssetIn(BaseModel):
    name: str
    kind: str = "currency"
    category: str = ""
    interest_basis: str = ""
    profile: str = ""
    icon: str = ""
    units: str = ""
    wrapper: str = ""

    @field_validator("wrapper")
    @classmethod
    def _validate_wrapper(cls, v):
        return _check_wrapper(v)


class AssetUpdate(BaseModel):
    """Every field optional: only what is given gets changed."""

    name: str | None = None
    category: str | None = None
    profile: str | None = None
    icon: str | None = None
    wrapper: str | None = None

    @field_validator("wrapper")
    @classmethod
    def _validate_wrapper(cls, v):
        return _check_wrapper(v)


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    category: str
    interest_basis: str
    profile: str
    icon: str
    units: str
    wrapper: str
    created_at: datetime

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)
