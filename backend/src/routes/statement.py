"""Statement import assistant on the server (services/statement_assist.py).

Only for a wallet that chose "on the server" in Settings
(PUT /api/settings/statement-assist); with "in this browser" the same jobs run
in the browser and nothing reaches these endpoints. The request body is the
part of the statement the job needs; it is never stored, and nothing from it
is logged - not even on a model failure, whose message would carry it.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models.settings import Setting
from ..schemas.statement import ColumnsIn, ExtractIn, MatchIn
from ..services import llm, statement_assist

router = APIRouter(prefix="/api/statement", tags=["statement"])


def statement_assist_mode(db: Session) -> str:
    row = db.query(Setting).filter(Setting.key == "statement_assist").first()
    return row.value if row and row.value in ("off", "browser", "server") else "off"


def _server_mode(db: Session = Depends(get_db)) -> None:
    if statement_assist_mode(db) != "server":
        raise HTTPException(409, "The statement assistant is not set to run on the server.")
    if not llm.configured():
        raise HTTPException(503, "No model is configured on this server.")


def _run(job):
    try:
        return job()
    except llm.LLMUnavailable:
        # The reason is not passed on: it can quote the request, i.e. statement text.
        raise HTTPException(503, "The model did not answer in time. Try again.") from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "The model returned an answer that could not be read.") from None


@router.post("/columns", dependencies=[Depends(_server_mode)])
def columns(payload: ColumnsIn):
    return _run(lambda: statement_assist.columns(payload.header, payload.sample))


@router.post("/extract", dependencies=[Depends(_server_mode)])
def extract(payload: ExtractIn):
    return {"transactions": _run(lambda: statement_assist.extract(payload.lines, payload.first_line))}


@router.post("/match", dependencies=[Depends(_server_mode)])
def match(payload: MatchIn):
    return {
        "matches": _run(
            lambda: statement_assist.match(
                [c.model_dump() for c in payload.commitments],
                [p.model_dump() for p in payload.payments],
            )
        )
    }
