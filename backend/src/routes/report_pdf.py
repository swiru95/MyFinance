"""Wallet PDF report: current holdings, allocation, a value-over-time chart
and "your money vs growth" efficiency for a chosen period, downloadable
immediately - plus an optional AI commentary section, generated through the
same LLM queue as the other insights (see services/insights.py's
"wallet_pdf" kind, driven by routes/insights.py exactly like profile/digest/
next_steps) and only embedded once that job has actually finished.

Per-user scoping needs nothing special here: `db` is a session confined to the
caller's rows (deps.get_db, scoping.py), so both the freshly built snapshot and
an `ai_insight_id` lookup can only see their own data - another user's
insight id is a 404, exactly as if it did not exist. Nothing identifying the
user (name, email, subject) is ever put into the PDF.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import TERMS_VERSION
from ..deps import get_db
from ..models.insight import Insight
from ..schemas.insight import INSIGHT_LANGUAGES
from ..services import wallet_report
from ..services.efficiency import PERIODS
from ..timeutils import as_utc
from .helpers import get_timezone

router = APIRouter(prefix="/api/reports", tags=["reports"])

_PERIOD_PATTERN = "^(" + "|".join(PERIODS) + ")$"
_LANGUAGE_PATTERN = "^(" + "|".join(INSIGHT_LANGUAGES) + ")$"


@router.get("/pdf")
def download_pdf(
    period: str = Query("all", pattern=_PERIOD_PATTERN),
    language: str = Query("en", pattern=_LANGUAGE_PATTERN),
    ai_insight_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Build and stream the report. `ai_insight_id`, when given, must name a
    *done* "wallet_pdf" Insight in the same language and period - anything
    else (still running, wrong kind, mismatched period/language) is a 409
    rather than silently downloading the report without it, since the
    person just watched that job for a reason.

    With `ai_insight_id`, the whole PDF - not just the AI section - is
    rendered from that insight's own stored `snapshot`, not a freshly built
    one: crypto/metal prices move between generating the commentary and
    downloading the PDF, and the tables and the commentary must describe
    the same numbers or the AI text could end up narrating a figure the
    page next to it no longer shows. The "data as of" line on page 1 then
    shows when that snapshot was actually taken, which can be noticeably
    earlier than "now".
    """
    ai_content: str | None = None
    ai_created_at = None
    ai_ungrounded: list[str] = []
    snapshot: dict

    if ai_insight_id is not None:
        row = db.query(Insight).filter(Insight.id == ai_insight_id).first()
        if row is None:
            raise HTTPException(404, "No such insight")
        if row.kind != "wallet_pdf":
            raise HTTPException(409, "That insight is not a wallet report commentary")
        if row.status != "done":
            raise HTTPException(409, f"AI commentary is not ready yet (status: {row.status})")
        if row.language != language:
            raise HTTPException(409, "AI commentary language does not match the report")
        if (row.period or "all") != period:
            raise HTTPException(409, "AI commentary period does not match the report")
        snapshot = row.snapshot
        ai_content = row.content
        ai_ungrounded = row.ungrounded or []
        # Stored naive-but-UTC (see timeutils.as_utc); shown in the app's
        # configured zone like every other timestamp in this PDF, not UTC.
        ai_created_at = as_utc(row.created_at).astimezone(ZoneInfo(get_timezone(db)))
    else:
        snapshot = wallet_report.build_snapshot(db, period)

    pdf_bytes = wallet_report.build_pdf(
        snapshot, language, TERMS_VERSION,
        ai_content=ai_content, ai_created_at=ai_created_at, ai_ungrounded=ai_ungrounded,
    )
    filename = f"myfinance-report-{period}-{language}.pdf"
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
