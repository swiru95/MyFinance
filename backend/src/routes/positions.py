"""Position CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.position import PositionIn, PositionOut, PositionUpdate
from ..models.asset import Asset
from ..models.position import Position
from .helpers import get_asset, compute_value

router = APIRouter(prefix="/api/positions", tags=["positions"])


def _latest_snapshot(db: Session, asset_id: int) -> Position | None:
    """The most recent existing row for an asset, before any new one is added."""
    return (
        db.query(Position)
        .filter(Position.asset_id == asset_id)
        .order_by(Position.timestamp.desc(), Position.id.desc())
        .first()
    )


def _flow_in_base(
    asset: Asset,
    flow: float | None,
    new_amount: float,
    price: float,
    previous: Position | None,
) -> float | None:
    """Money moved into (+) or out of (-) this asset, in base currency.

    None means unknown, not zero: an opening balance (no previous snapshot)
    is never a flow, and a currency snapshot with no `flow` given says
    nothing about whether money moved.

    - currency: `flow` is in the payload's own currency; `price` is the FX
      rate compute_value used for this snapshot, so multiplying converts it.
    - gold/crypto: a given `flow` is already in base currency (the user paid
      a different price than today's); otherwise it is derived from the
      change in amount at today's price, which needs a previous snapshot.
    - interest: base currency as-is, never derived from the amount (the
      amount there is a principal, not a holding size a price multiplies).
    """
    if asset.kind == "currency":
        return None if flow is None else flow * price
    if asset.kind in ("gold", "crypto"):
        if flow is not None:
            return flow
        if previous is None:
            return None
        return (new_amount - float(previous.amount)) * price
    return flow  # interest


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
    previous = _latest_snapshot(db, asset.id)
    value, price, base = compute_value(
        db, asset, payload.amount, payload.currency, payload.accrues_from
    )
    flow_in_base = _flow_in_base(asset, payload.flow, payload.amount, price, previous)
    pos = Position(
        asset_id=asset.id,
        amount=payload.amount,
        currency=payload.currency,
        value_in_base=round(value, 4),
        price_used=round(price, 6),
        base_currency=base,
        notes=payload.notes,
        accrues_from=payload.accrues_from,
        flow_in_base=round(flow_in_base, 4) if flow_in_base is not None else None,
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
    previous = _latest_snapshot(db, asset.id)
    value, price, base = compute_value(
        db, asset, payload.amount, payload.currency, payload.accrues_from
    )
    flow_in_base = _flow_in_base(asset, payload.flow, payload.amount, price, previous)
    snapshot = Position(
        asset_id=asset.id,
        amount=payload.amount,
        currency=payload.currency,
        value_in_base=round(value, 4),
        price_used=round(price, 6),
        base_currency=base,
        notes=payload.notes,
        accrues_from=payload.accrues_from,
        flow_in_base=round(flow_in_base, 4) if flow_in_base is not None else None,
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
