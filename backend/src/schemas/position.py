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
    # Money moved into (+) or out of (-) the asset for this snapshot. See
    # routes/positions.py for how it is interpreted per asset kind.
    flow: float | None = None


class PositionUpdate(BaseModel):
    amount: float
    currency: str = "PLN"
    notes: str = ""
    accrues_from: date | None = None
    flow: float | None = None


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
    flow_in_base: float | None
    timestamp: datetime

    @field_serializer("timestamp")
    def _utc(self, value):
        return as_utc(value)
