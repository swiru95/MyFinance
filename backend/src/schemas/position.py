"""Position schemas."""
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..timeutils import as_utc


class PositionIn(BaseModel):
    asset_id: int
    amount: float = Field(..., description="Currency amount, grams (gold), coin quantity (crypto) or principal (interest)")
    currency: str = "PLN"
    notes: str = ""
    accrues_from: date | None = None


class PositionUpdate(BaseModel):
    amount: float
    currency: str = "PLN"
    notes: str = ""
    accrues_from: date | None = None


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    amount: float
    currency: str
    value_in_base: float
    price_used: float
    base_currency: str
    notes: str
    accrues_from: date | None
    timestamp: datetime

    @field_serializer("timestamp")
    def _utc(self, value):
        return as_utc(value)
