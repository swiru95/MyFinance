"""A written assessment of the portfolio, produced by a local language model.

Generation takes minutes - the router holds one model in memory at a time, so
a request can be waiting on a 76 GB model being loaded before the first token.
That is far too long to hold an HTTP request open through the gateway, so a row
is created immediately in the "pending" state and filled in by a worker thread.
The frontend polls it.

The snapshot the model was given is stored alongside the text. An assessment
read six months later is only interpretable next to the figures that produced
it, and those figures have moved on by then.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    # pending -> running -> translating -> done, or failed from any of them.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # One of config.REPORT_STYLES: the wallet style the model judges against.
    style: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    # The finished report in `language`, as Markdown.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Kept when the report was translated, so the original is never lost to a
    # translation that turned out to be poor.
    content_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    translator: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The figures handed to the model, as the assessment endpoint built them.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report {self.id} {self.style}/{self.language} {self.status}>"
