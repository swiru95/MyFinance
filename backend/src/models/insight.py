"""LLM-produced insights: profile analysis, monthly digest, next-best-step
ranking.

Same pattern as models/report.py - generation takes minutes (the router
holds one model resident at a time), so a row is created "pending" and a
worker thread fills it in place while the frontend polls. The snapshot (and
for profile/next_steps, the structured `data` the model reasoned over) is
kept alongside the text so a reading of it months later is still
interpretable against the figures that produced it, not today's.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True
    )
    # profile | digest | next_steps
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # "YYYY-MM" for a digest, "" for profile/next_steps.
    period: Mapped[str] = mapped_column(String(7), nullable=False, default="")
    # pending -> running -> translating -> done, or failed from any of them.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    # The finished text in `language`, as Markdown.
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Kept when translated, so the original is never lost to a poor translation -
    # same reasoning as Report.content_en.
    content_en: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # The model's structured JSON answer (profile: tolerance/capacity/
    # mismatches/priorities; next_steps: ranked steps). Empty for digest,
    # which is free-form Markdown like a wallet report.
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # `data` with only its prose fields translated to Polish in one model
    # call (profile: summary_md, priorities[], mismatches[].about/stated/
    # actual/why_it_matters; next_steps: steps[].title/why_md) - enum
    # fields and keys are copied through untouched. Only ever set for
    # language "pl" on profile/next_steps, whose tabs render `data` as
    # prose rather than through `content`/`content_en`. Stays None when
    # translation was never attempted (en jobs, digest) or when it failed -
    # the reason for a failure is appended to `error` without failing the
    # job, and the frontend falls back to the English `data` with a note.
    data_localized: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    # The figures the model was given, so `content_en` stays interpretable
    # once the underlying numbers have moved on.
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Numbers in `content_en` the grounding check could not match to
    # `snapshot` (services/grounding.py), plus - for next_steps - any ranked
    # key the model invented that was not one of the candidate rungs. Never
    # silently dropped, only flagged; the UI shows a warning.
    ungrounded: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    translator: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Insight {self.id} {self.kind}/{self.period} {self.status}>"
