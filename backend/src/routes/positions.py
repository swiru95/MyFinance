"""Position CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.position import PositionIn, PositionOut, PositionUpdate
from ..models.position import Position
from .helpers import get_asset, compute_value

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("", response_model=list[PositionOut])
def list_positions(db: Session = Depends(get_db)):
    """Latest position for each asset."""
    rows = (
        db.query(Position)
        .order_by(Position.asset_id, Position.timestamp.desc())
        .all()
    )
    seen: set[int] = set()
    out = []
    for r in rows:
        if r.asset_id in seen:
            continue
        seen.add(r.asset_id)
        out.append(r)
    return out


@router.post("", response_model=PositionOut, status_code=201)
def create_position(payload: PositionIn, db: Session = Depends(get_db)):
    asset = get_asset(db, payload.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    value, price, base = compute_value(
        db, asset, payload.amount, payload.currency, payload.accrues_from
    )
    pos = Position(
        asset_id=asset.id,
        amount=payload.amount,
        currency=payload.currency,
        value_in_base=round(value, 4),
        price_used=round(price, 6),
        base_currency=base,
        notes=payload.notes,
        accrues_from=payload.accrues_from,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return pos


@router.get("/{position_id}/history", response_model=list[PositionOut])
def position_history(position_id: int, db: Session = Depends(get_db)):
    """All updates for the asset that owns this position (time series)."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    return (
        db.query(Position)
        .filter(Position.asset_id == pos.asset_id)
        .order_by(Position.timestamp.asc())
        .all()
    )


@router.get("/{position_id}", response_model=PositionOut)
def get_position(position_id: int, db: Session = Depends(get_db)):
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    return pos


@router.put("/{position_id}", response_model=PositionOut)
def update_position(position_id: int, payload: PositionUpdate, db: Session = Depends(get_db)):
    """Update a position by recording a NEW timestamped snapshot for the same asset.

    This keeps the full history so the progress can be charted over time.
    """
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    asset = get_asset(db, pos.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    value, price, base = compute_value(
        db, asset, payload.amount, payload.currency, payload.accrues_from
    )
    snapshot = Position(
        asset_id=asset.id,
        amount=payload.amount,
        currency=payload.currency,
        value_in_base=round(value, 4),
        price_used=round(price, 6),
        base_currency=base,
        notes=payload.notes,
        accrues_from=payload.accrues_from,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.delete("/{position_id}", status_code=204)
def delete_position(position_id: int, db: Session = Depends(get_db)):
    """Delete the whole history for the asset of this position."""
    pos = db.query(Position).filter(Position.id == position_id).first()
    if not pos:
        raise HTTPException(404, "Position not found")
    db.query(Position).filter(Position.asset_id == pos.asset_id).delete()
    db.commit()
