"""LLM insight endpoints: profile analysis, monthly digest, next-best-step
ranking, and the deterministic ladder they rank against.

Generation runs on a worker thread for the same reason as routes/reports.py:
the model server holds one model in memory at a time, so a request can wait
minutes on a model being loaded - far longer than the gateway holds a
connection open. POST returns a pending row immediately and the frontend
polls it.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models.insight import Insight
from ..schemas.insight import (
    INSIGHT_KINDS,
    InsightIn,
    InsightOut,
    InsightStatus,
    InsightSummary,
    LadderOut,
    LadderStateIn,
    ProfileAnswers,
)
from ..services import insights
from ..services import ladder as ladder_service
from ..services import llm

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _validate_kind(kind: str) -> str:
    if kind not in INSIGHT_KINDS:
        raise HTTPException(404, f"No such insight kind: {kind}")
    return kind


def _generate(insight_id: int) -> None:
    """Write one insight, start to finish, on a worker thread.

    Owns its own session: the request that queued this has long since
    returned and closed its own.
    """
    db = SessionLocal()
    try:
        insight = db.query(Insight).filter(Insight.id == insight_id).first()
        if insight is None:
            return
        insights.generate(db, insight)
    finally:
        db.close()


@router.get("/status", response_model=InsightStatus)
def status():
    """Whether a model is configured, so the page can say so before trying."""
    return InsightStatus(
        configured=llm.configured(),
        model=settings.llm_model,
        translator=settings.llm_translate_model,
    )


@router.get("/profile/answers", response_model=ProfileAnswers)
def get_profile_answers(db: Session = Depends(get_db)):
    return insights.load_profile_answers(db)


@router.put("/profile/answers", response_model=ProfileAnswers)
def put_profile_answers(payload: ProfileAnswers, db: Session = Depends(get_db)):
    insights.save_profile_answers(db, payload)
    return payload


def _ladder_out(db: Session) -> LadderOut:
    rungs = ladder_service.build_ladder(db)
    return LadderOut(
        rungs=rungs,
        feedback={r["key"]: r["feedback"] for r in rungs if r.get("feedback")},
    )


@router.get("/ladder", response_model=LadderOut)
def get_ladder(db: Session = Depends(get_db)):
    return _ladder_out(db)


@router.put("/ladder/{key}", response_model=LadderOut)
def put_ladder_state(key: str, payload: LadderStateIn, db: Session = Depends(get_db)):
    if key not in ladder_service.RUNG_KEYS:
        raise HTTPException(404, f"No such ladder key: {key}")
    ladder_service.save_feedback_entry(db, key, payload.state)
    # The whole ladder is recomputed and returned rather than just the one
    # rung's feedback, so the page can repaint the checklist from one call.
    return _ladder_out(db)


@router.get("/item/{insight_id}", response_model=InsightOut)
def get_item(insight_id: int, db: Session = Depends(get_db)):
    row = db.query(Insight).filter(Insight.id == insight_id).first()
    if row is None:
        raise HTTPException(404, "No such insight")
    return row


@router.delete("/item/{insight_id}", status_code=204)
def delete_item(insight_id: int, db: Session = Depends(get_db)):
    row = db.query(Insight).filter(Insight.id == insight_id).first()
    if row is None:
        raise HTTPException(404, "No such insight")
    db.delete(row)
    db.commit()


@router.get("", response_model=list[InsightSummary])
def list_items(limit: int = 50, db: Session = Depends(get_db)):
    """Past insights of every kind, newest first."""
    return (
        db.query(Insight)
        .order_by(Insight.created_at.desc(), Insight.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


@router.post("/{kind}", response_model=InsightOut, status_code=202)
def create_insight(kind: str, payload: InsightIn, db: Session = Depends(get_db)):
    """Queue a profile/digest/next_steps job and return the row to poll."""
    _validate_kind(kind)
    if not llm.configured():
        raise HTTPException(503, "No model is configured for insights")

    row = Insight(
        kind=kind,
        period=payload.period or "",
        language=payload.language,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Daemon so a shutdown is never held up by a generation in flight; the
    # row stays "running" in that case and the page offers to generate again.
    threading.Thread(target=_generate, args=(row.id,), daemon=True).start()
    return row


@router.get("/{kind}/latest", response_model=InsightOut)
def latest_insight(kind: str, language: str = "en", db: Session = Depends(get_db)):
    _validate_kind(kind)
    row = (
        db.query(Insight)
        .filter(Insight.kind == kind, Insight.status == "done", Insight.language == language)
        .order_by(Insight.created_at.desc(), Insight.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(404, f"No completed {kind} insight in {language}")
    return row
