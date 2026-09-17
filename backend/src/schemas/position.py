"""Position schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..timeutils import as_utc


class PositionIn(BaseModel):
    asset_id: int
    amount: float = Field(..., description="Currency amount, grams (gold) or coin quantity (crypto)")
    currency: str = "PLN"
    notes: str = ""


class PositionUpdate(BaseModel):
    amount: float
    currency: str = "PLN"
    notes: str = ""


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
    timestamp: datetime

    @field_serializer("timestamp")
    def _utc(self, value):
        return as_utc(value)
