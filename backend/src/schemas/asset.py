"""Asset schemas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer

from ..timeutils import as_utc


class AssetIn(BaseModel):
    name: str
    kind: str = "currency"
    category: str = ""
    icon: str = ""
    units: str = ""


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    category: str
    icon: str
    units: str
    created_at: datetime

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)
