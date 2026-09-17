"""Wallet assessment endpoints.

Generation runs on a worker thread rather than in the request. The router on
the model server holds one model in memory at a time, so a request can be
waiting several minutes on a 76 GB model being loaded before the first token
appears - far longer than the gateway will hold a connection open. POST
therefore returns a pending row immediately and the frontend polls it.
"""
from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models.report import Report
from ..schemas.report import ReportIn, ReportOut, ReportStatus, ReportSummary
from ..services import assessment, llm

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _generate(report_id: int) -> None:
    """Write one report, start to finish, on a worker thread.

    Owns its own session: the request that queued this has long since returned
    and closed its own.
    """
    db = SessionLocal()
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if report is None:
            return
        try:
            report.status = "running"
            db.commit()

            snapshot = assessment.build_snapshot(db)
            report.snapshot = snapshot
            db.commit()

            english, model = assessment.write_report(snapshot, report.style)
            report.content_en = english
            report.model = model

            if report.language == "pl":
                # Stored before translating, so a translation failure leaves a
                # readable English report behind rather than nothing at all.
                report.content = english
                report.status = "translating"
                db.commit()
                polish, translator = assessment.translate_to_polish(english)
                report.content = polish
                report.translator = translator
            else:
                report.content = english

            report.status = "done"
            db.commit()
        except llm.LLMUnavailable as exc:
            report.status = "failed"
            report.error = str(exc)
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            # A worker thread that dies silently would leave the row stuck on
            # "running" and the page polling forever.
            report.status = "failed"
            report.error = f"Unexpected error: {exc}"
            db.commit()
    finally:
        db.close()


@router.get("/status", response_model=ReportStatus)
def status():
    """Whether a model is configured, so the page can say so before trying."""
    from ..config import REPORT_STYLES

    return ReportStatus(
        configured=llm.configured(),
        model=settings.llm_model,
        translate_model=settings.llm_translate_model,
        styles=REPORT_STYLES,
        mtls=llm.using_mtls(),
        tls_verified=bool(settings.llm_ca_bundle) or settings.llm_verify_tls,
    )


@router.get("", response_model=list[ReportSummary])
def list_reports(limit: int = 20, db: Session = Depends(get_db)):
    """Past assessments, newest first."""
    return (
        db.query(Report)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )


@router.post("", response_model=ReportOut, status_code=202)
def create_report(payload: ReportIn, db: Session = Depends(get_db)):
    """Queue an assessment and return the row to poll."""
    if not llm.configured():
        raise HTTPException(503, "No model is configured for assessments")

    report = Report(style=payload.style, language=payload.language, status="pending")
    db.add(report)
    db.commit()
    db.refresh(report)

    # Daemon so a shutdown is never held up by a generation in flight; the row
    # stays "running" in that case and the page offers to generate again.
    threading.Thread(target=_generate, args=(report.id,), daemon=True).start()
    return report


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(404, "No such report")
    return report


@router.delete("/{report_id}", status_code=204)
def delete_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(404, "No such report")
    db.delete(report)
    db.commit()
