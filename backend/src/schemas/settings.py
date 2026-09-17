"""Settings schemas."""
from pydantic import BaseModel, Field, field_validator

from ..config import TIMEZONES


class SettingsIn(BaseModel):
    base_currency: str = Field(..., pattern="^(PLN|EUR|USD|CHF)$")
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, v: str | None) -> str | None:
        if v is not None and v not in TIMEZONES:
            raise ValueError(f"timezone must be one of: {', '.join(TIMEZONES)}")
        return v
