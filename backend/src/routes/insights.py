"""LLM insight endpoints: profile analysis, monthly digest, next-best-step
ranking, and the deterministic ladder they rank against.

Generation runs off the request, on the process-wide LLM queue (see
services/llm_queue.py) for the same reason as routes/reports.py: the model
server holds one model in memory at a time, so two generations firing
together thrash it, and a request can wait minutes on a model being loaded -
far longer than the gateway holds a connection open. POST returns a pending
row immediately and the frontend polls it.
"""
from __future__ import annotations

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
from ..services import llm, llm_queue

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _validate_kind(kind: str) -> str:
    if kind not in INSIGHT_KINDS:
        raise HTTPException(404, f"No such insight kind: {kind}")
    return kind


def _generate(insight_id: int) -> None:
    """Write one insight, start to finish, on the shared LLM queue's worker.

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

    # Queued rather than started immediately - see services/llm_queue.py for
    # why. The row stays "pending" until the shared worker actually picks it
    # up, then "running" in that case if a shutdown cuts it off mid-job, and
    # the page offers to generate again either way.
    row_id = row.id
    llm_queue.enqueue(lambda: _generate(row_id))
    return row


@router.get("/{kind}/latest", response_model=InsightOut)
def latest_insight(kind: str, language: str = "en", db: Session = Depends(get_db)):
    """The newest `kind` insight in `language`, whatever its status.

    Not filtered to "done": the Profile and Next steps tabs call this on
    mount to resume whatever job is already on screen after a tab switch
    remounts them, same as the wallet-assessment tab's own history lookup -
    filtering to "done" here meant a pending, translating or failed job was
    invisible until it happened to finish, with no way to see it was even
    running or that it had failed.
    """
    _validate_kind(kind)
    row = (
        db.query(Insight)
        .filter(Insight.kind == kind, Insight.language == language)
        .order_by(Insight.created_at.desc(), Insight.id.desc())
        .first()
    )
    if row is None:
        raise HTTPException(404, f"No {kind} insight in {language} yet")
    return row
