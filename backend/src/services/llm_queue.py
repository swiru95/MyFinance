"""A single process-wide serial queue for LLM jobs.

Reports (routes/reports.py) and insights (routes/insights.py) each used to
spawn their own worker thread the moment a job was queued, so two jobs fired
close together ran their generations concurrently. The router in front of
llama-server holds exactly one model resident at a time, so two concurrent
generations - a report and a digest, or two insights - fight over the same
slot: one blocks on a model swap it triggered while the other was mid
generation, both threads' timeouts start ticking, and the requests thrash or
time out instead of simply running one after the other.

Every job that talks to the model now goes through `enqueue` instead of
starting its own thread, and one long-lived worker thread pulls jobs off the
queue and runs them one at a time. A row's own status is unaffected by this:
it is created "pending" as before, and only the job function itself (still
routes/reports.py:_generate or routes/insights.py:_generate) flips it to
"running" once the worker actually calls it - so a job queued behind others
now simply stays "pending" for longer, which is exactly the visible
behaviour the frontend already polls for.
"""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from sqlalchemy import text

from .. import rls

logger = logging.getLogger(__name__)

# What a job left behind by a crash or restart is told lives in models/jobnotes
# (the note codes the sweep writes, and the text they stand for). Re-exported
# here because tests and callers import them from this module.
from ..models.jobnotes import (  # noqa: E402
    INTERRUPTED,
    INTERRUPTED_NOTE,
    TRANSLATION_INTERRUPTED,
    TRANSLATION_INTERRUPTED_NOTE,
)

_jobs: "queue.Queue[Callable[[], None]]" = queue.Queue()
_worker_lock = threading.Lock()
_worker_started = False


def _run_forever() -> None:
    while True:
        job = _jobs.get()
        try:
            job()
        except Exception:  # pragma: no cover - defensive
            # Each job (routes/reports.py:_generate, routes/insights.py:
            # _generate) is responsible for catching its own errors and
            # writing them onto its own row. This is only a backstop so one
            # job blowing up in a way its own try/except did not anticipate
            # can never kill the worker thread and silently wedge every job
            # queued behind it.
            logger.exception("Unhandled error running a queued LLM job")
        finally:
            _jobs.task_done()


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        # Daemon so a shutdown is never held up by a generation in flight;
        # whatever job was running stays in its "running" state and the page
        # offers to generate again, same as before this queue existed.
        threading.Thread(target=_run_forever, daemon=True, name="llm-queue-worker").start()
        _worker_started = True


def enqueue(job: Callable[[], None]) -> None:
    """Queue one LLM job to run once every job ahead of it has finished.

    Starts the single worker thread on first use. `job` takes no arguments -
    callers close over whatever id/args it needs, e.g.
    `enqueue(lambda: _generate(ring, report.id))`. Every job is closed over the
    user who queued it - and a *copy of that user's key ring*, handed over in
    memory by the request, which is what lets the job read and write the
    encrypted figures - and opens its own session scoped to that user. The queue
    itself is shared by all users but knows nothing about them, and holds a key
    only as long as a job that closes over it is waiting.
    """
    _ensure_worker()
    _jobs.put(job)


def cleanup_interrupted_jobs() -> None:
    """Sweep both Report and Insight tables on startup to clean up orphaned
    jobs left by a crash/restart while they were pending/running/translating.

    Rows in 'translating' -> mark done, with a note code saying the translation
    was cut short (the English text is always stored before that status is set,
    so there is something to show). All other pending/running/translating rows
    -> mark failed, with a note code saying the job was interrupted.

    Continues on errors to never block startup.

    Deliberately works across every user: it runs once, before any request, and
    only ever changes the status of rows - it reads no content, holds no key and
    builds no prompt. It *cannot* decrypt, which is why the note is a plaintext
    code (`status_note`) that the model turns back into text, not the encrypted
    `error` column. On PostgreSQL the application's role cannot see other users'
    rows at all (row-level security, rls.py), so this is one call to a SECURITY
    DEFINER function that does exactly this sweep and nothing else. On SQLite
    there is no such boundary and a system session does it directly, with
    statements that never load a row (so never touch an encrypted column).
    """
    from ..database import engine

    if engine.dialect.name == "postgresql":
        try:
            with engine.begin() as conn:
                reports, insights = conn.execute(
                    text(f"SELECT out_reports, out_insights FROM public.{rls.SWEEP_JOBS}()")
                ).one()
            if reports:
                logger.info(f"Cleaned up {reports} interrupted Report rows")
            if insights:
                logger.info(f"Cleaned up {insights} interrupted Insight rows")
        except Exception:
            logger.exception("Error cleaning up interrupted jobs")
        return

    from sqlalchemy import case, update

    from ..scoping import open_system_session
    from ..models.report import Report
    from ..models.insight import Insight

    db = open_system_session()
    try:
        for model, label in ((Report, "Report"), (Insight, "Insight")):
            try:
                result = db.execute(
                    update(model)
                    .where(model.status.in_(("pending", "running", "translating")))
                    .values(
                        status=case((model.status == "translating", "done"), else_="failed"),
                        status_note=case(
                            (model.status == "translating", TRANSLATION_INTERRUPTED),
                            else_=INTERRUPTED,
                        ),
                    )
                    .execution_options(synchronize_session=False)
                )
                db.commit()
                if result.rowcount:
                    logger.info(f"Cleaned up {result.rowcount} interrupted {label} rows")
            except Exception:
                db.rollback()
                logger.exception(f"Error cleaning up {label} rows")
    finally:
        db.close()
