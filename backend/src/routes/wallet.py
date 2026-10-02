"""Wallet export and import (see services/wallet_io.py and schemas/wallet.py).

  GET  /api/wallet/export          download the setup as one JSON file
  POST /api/wallet/import/preview  dry run: what would be created, what conflicts
  POST /api/wallet/import          write it (one transaction), same body

The import body is the file itself, raw. It is read with a hard size cap before
it is parsed, validated as a whole, and only then planned and written - so a
rejected file leaves no trace. Everything goes through the caller's own
user-scoped, encrypting session.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..auth import Principal, require_user
from ..deps import get_db
from ..schemas.wallet import FORMAT, MAX_FILE_BYTES, VERSION, ImportPlanOut, WalletFile
from ..services import wallet_io

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


async def wallet_body(request: Request) -> bytes:
    """The raw request body, refused as soon as it passes the size limit."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        raise HTTPException(413, f"The file is larger than {MAX_FILE_BYTES} bytes")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, f"The file is larger than {MAX_FILE_BYTES} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_wallet(raw: bytes) -> WalletFile:
    """The whole file, validated; or an HTTP error and nothing else."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise HTTPException(400, "The file is not valid JSON") from None
    if not isinstance(data, dict):
        raise HTTPException(400, "The file is not a MyFinance wallet file")
    if data.get("format") != FORMAT:
        raise HTTPException(422, f'Not a MyFinance wallet file (format must be "{FORMAT}")')
    version = data.get("version")
    if version != VERSION or isinstance(version, bool):
        raise HTTPException(
            422,
            f"Unsupported wallet file version {json.dumps(version)[:20]}; "
            f"this server reads version {VERSION}",
        )
    try:
        return WalletFile.model_validate(data)
    except ValidationError as exc:
        errors = [
            {"where": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ][:20]
        raise HTTPException(
            422, detail={"message": "The wallet file is not valid", "errors": errors}
        ) from None


@router.get("/export")
def export_wallet(db: Session = Depends(get_db), principal: Principal = Depends(require_user)):
    payload = wallet_io.build_export(db, principal.user_id)
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return Response(
        body.encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="myfinance-wallet-{date.today().isoformat()}.json"',
            # A file of someone's finances: never keep it in a shared cache.
            "Cache-Control": "no-store",
        },
    )


@router.post("/import/preview", response_model=ImportPlanOut)
def preview_import(
    raw: bytes = Depends(wallet_body),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    return wallet_io.preview(db, principal.user_id, parse_wallet(raw))


@router.post("/import", response_model=ImportPlanOut)
def run_import(
    raw: bytes = Depends(wallet_body),
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_user),
):
    return wallet_io.apply(db, principal.user_id, parse_wallet(raw))
