"""Wallet assessment endpoints.

Generation runs off the request, on the process-wide LLM queue (see
services/llm_queue.py) rather than in a thread of its own: the router on the
model server holds one model in memory at a time, so two generations firing
together thrash it, and a single request can be waiting several minutes on a
76 GB model being loaded before the first token appears - far longer than the
gateway will hold a connection open. POST therefore returns a pending row
immediately and the frontend polls it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..auth import Principal, require_user
from ..config import settings
from ..deps import get_db
from ..models.report import Report
from ..crypto.core import KeyExpired, KeyRing
from ..scoping import open_session
from ..schemas.report import ReportIn, ReportOut, ReportStatus, ReportSummary
from ..services import assessment, llm, llm_queue

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _generate(keyring: KeyRing, report_id: int) -> None:
    """Write one report, start to finish, on the shared LLM queue's worker.

    Owns its own session: the request that queued this has long since returned
    and closed its own. That session is scoped to the user who queued the job,
    so the snapshot the model is shown can only ever be built from their rows,
    and a job whose id belongs to someone else finds no report and does nothing.

    `keyring` is the user's data key, handed over in memory by the request that
    queued the job (a copy that expires after settings.job_key_seconds); the
    row's prompt and answer are encrypted, and this is the only way the worker
    can read the figures it is asked to write about or store what it wrote. It
    is destroyed when the job ends, however it ends.
    """
    db = open_session(keyring.user_id, keyring)
    try:
        try:
            keyring.export_dek()
        except KeyExpired:
            _fail_expired(db, Report, report_id)
            return
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
                try:
                    polish, translator = assessment.translate_to_polish(english)
                    report.content = polish
                    report.translator = translator
                except llm.LLMUnavailable as exc:
                    # The English report is already a finished, useful
                    # result - losing it to a translation hiccup would throw
                    # away a good assessment over one extra model call, so
                    # this degrades to English-with-a-note rather than
                    # failing the whole job.
                    report.error = f"Could not translate to Polish, showing English: {exc}"
            else:
                report.content = english

            report.status = "done"
            db.commit()
        except llm.LLMUnavailable as exc:
            report.status = "failed"
            report.error = str(exc)
            db.commit()
        except Exception as exc:  # pragma: no cover - defensive
            # A job that dies silently would leave the row stuck on
            # "running" and the page polling forever.
            report.status = "failed"
            report.error = f"Unexpected error: {exc}"
            db.commit()
    finally:
        db.close()
        keyring.destroy()


def _fail_expired(db, model, row_id: int) -> None:
    """The key ran out before the job could use it (it sat in the queue longer
    than settings.job_key_seconds). It cannot write an encrypted `error` without
    the key, so the row fails with a plaintext note code instead."""
    from ..models.jobnotes import KEY_EXPIRED

    db.execute(
        update(model)
        .where(model.id == row_id)
        .values(status="failed", status_note=KEY_EXPIRED)
        .execution_options(synchronize_session=False)
    )
    db.commit()


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
def create_report(
    payload: ReportIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Queue an assessment and return the row to poll."""
    if not llm.configured():
        raise HTTPException(503, "No model is configured for assessments")

    report = Report(style=payload.style, language=payload.language, status="pending")
    db.add(report)
    db.commit()
    db.refresh(report)

    # Queued rather than started immediately - see services/llm_queue.py for
    # why. The row stays "pending" until the shared worker actually picks it
    # up, then "running" in that case if a shutdown cuts it off mid-job, and
    # the page offers to generate again either way.
    report_id = report.id
    # The job runs after this request has returned, so it gets its own copy of
    # the user's key, with its own (separately bounded) allowance.
    ring = principal.keyring.fork(settings.job_key_seconds)
    llm_queue.enqueue(lambda: _generate(ring, report_id))
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
