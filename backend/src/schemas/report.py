"""Wallet assessment schemas."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ..config import REPORT_LANGUAGES, REPORT_STYLES
from ..timeutils import as_utc


class ReportIn(BaseModel):
    style: str = Field("balanced", pattern="^(" + "|".join(REPORT_STYLES) + ")$")
    language: str = Field("en", pattern="^(" + "|".join(REPORT_LANGUAGES) + ")$")


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: str
    style: str
    language: str
    content: str
    model: str
    translator: str
    error: str

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)


class ReportSummary(BaseModel):
    """A history row: everything but the report text, which can be long."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    status: str
    style: str
    language: str
    model: str
    translator: str
    error: str

    @field_serializer("created_at")
    def _utc(self, value):
        return as_utc(value)


class ReportStatus(BaseModel):
    """Whether the feature can run at all, for the page to render against."""

    configured: bool
    model: str
    translate_model: str
    styles: list[str]
    # How this backend authenticates to the model server, so the page can show
    # that it is using a certificate rather than a shared key.
    mtls: bool = False
    tls_verified: bool = False
