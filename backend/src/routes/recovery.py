"""Recovery code endpoints.

The code is made here while the user is signed in with a working key, shown once,
and must be confirmed (typed back) before it counts. It is *used* here too, by a
sign-in whose identity is not the one that wrapped the data - the new, empty user
that an identity change creates. So the status and restore endpoints answer a
caller whose key could not be unlocked (`require_identity`); creating and
confirming need the unlocked key (`require_user`).

Every failed attempt looks the same (400) whatever was wrong with the code, and
repeated ones are refused with 429 and a Retry-After (services/recovery.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..auth import Principal, require_identity, require_user
from ..deps import get_db
from ..scoping import open_session
from ..schemas.recovery import CodeIn, CreateIn, CreatedOut, RestoreOut, StatusOut
from ..services import recovery as service

router = APIRouter(prefix="/api/recovery", tags=["recovery"])


def _refuse(exc: service.RecoveryError):
    if isinstance(exc, service.Throttled):
        return HTTPException(
            status_code=429,
            detail="Too many recovery attempts. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    if isinstance(exc, service.InvalidCode):
        return HTTPException(status_code=400, detail="That recovery code is not valid.")
    if isinstance(exc, service.NotEmpty):
        return HTTPException(
            status_code=409,
            detail="This account already holds data of its own, so a recovery code will not "
            "replace it. Sign in with the account you want to keep.",
        )
    if isinstance(exc, service.AlreadyConfigured):
        return HTTPException(
            status_code=409,
            detail="A recovery code already exists. Creating another makes the old one stop working; "
            "send replace=true to do that.",
        )
    return HTTPException(status_code=400, detail="Recovery failed.")


@router.get("/status", response_model=StatusOut)
def get_status(principal: Principal = Depends(require_identity)):
    """Whether this account has a recovery code, whether it was confirmed, and
    whether the caller is locked out of their data (their key cannot be unlocked
    with this sign-in, so the code is needed now)."""
    db = open_session(principal.user_id)
    try:
        return StatusOut(locked=principal.locked, **service.status(db, principal.user_id))
    finally:
        db.close()


@router.post("", response_model=CreatedOut, status_code=201)
def create_code(
    payload: CreateIn | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """Make a recovery code. It is in the response and nowhere else, ever: show it
    once, ask the user to save it, then call /confirm with it."""
    try:
        code = service.create(db, principal.keyring, replace=bool(payload and payload.replace))
    except service.RecoveryError as exc:
        raise _refuse(exc) from exc
    return JSONResponse(
        status_code=201,
        content=CreatedOut(code=code).model_dump(),
        headers={"Cache-Control": "no-store"},
    )


@router.post("/confirm", response_model=StatusOut)
def confirm_code(
    payload: CodeIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    """The user typed the code back: they have it."""
    try:
        service.confirm(db, principal.user_id, payload.code)
    except service.RecoveryError as exc:
        raise _refuse(exc) from exc
    return StatusOut(locked=False, **service.status(db, principal.user_id))


@router.post("/restore", response_model=RestoreOut)
def restore(payload: CodeIn, principal: Principal = Depends(require_identity)):
    """Re-attach the data a recovery code belongs to to this sign-in.

    For the new, empty account an identity change created (or an account whose
    key this sign-in cannot unlock). On success the caller's own account is gone
    and the next request is served as the restored one: the client should reload.
    """
    try:
        result = service.restore(principal.user_id, principal.key_secret(), payload.code)
    except service.RecoveryError as exc:
        raise _refuse(exc) from exc
    return JSONResponse(content=RestoreOut(restored=True, result=result).model_dump(), headers={"Cache-Control": "no-store"})
