"""Asset schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from ..services.price_service import CRYPTO_SYMBOLS, METAL_SYMBOLS
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

    @model_validator(mode="after")
    def _validate_units(self):
        """kind="crypto"/"metal" price by `units` (see price_service's
        catalogue), so a typo or unsupported symbol there would silently
        price as 0 (the crypto fallback for an unknown symbol) rather than
        fail loudly - reject it at creation instead."""
        u = self.units.upper()
        if self.kind == "crypto" and u not in CRYPTO_SYMBOLS:
            raise ValueError(
                f"units must be one of: {', '.join(sorted(CRYPTO_SYMBOLS))} for kind=crypto"
            )
        if self.kind == "metal" and u not in METAL_SYMBOLS:
            raise ValueError(
                f"units must be one of: {', '.join(sorted(METAL_SYMBOLS))} for kind=metal"
            )
        return self


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
