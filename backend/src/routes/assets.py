"""Asset type endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asset import Asset
from ..models.position import Position
from ..schemas.asset import AssetIn, AssetOut, AssetUpdate
from .helpers import compute_value, value_of_position

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("", response_model=list[AssetOut])
def list_assets(db: Session = Depends(get_db)):
    return db.query(Asset).order_by(Asset.id).all()


@router.post("", response_model=AssetOut, status_code=201)
def create_asset(payload: AssetIn, db: Session = Depends(get_db)):
    asset = Asset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.put("/{asset_id}", response_model=AssetOut)
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db)):
    """Edit an existing asset's descriptive fields.

    Not the kind or units - those decide how compute_value prices every past
    snapshot, so changing them after the fact would misprice the asset's own
    history.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    db.query(Position).filter(Position.asset_id == asset_id).delete()
    db.delete(asset)
    db.commit()


@router.post("/{asset_id}/archive", response_model=AssetOut)
def archive_asset(asset_id: int, db: Session = Depends(get_db)):
    """Soft delete: the asset disappears from "currently held" everywhere,
    but its snapshots stay so the portfolio-over-time chart is not rewritten.

    If the asset's latest snapshot still has a non-zero current value, a
    closing snapshot (amount/value 0) is written first, with the departing
    value recorded as an outflow - that is what turns its unrealised growth
    into realised growth on the growth endpoint (see services/growth.py).
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.archived_at is not None:
        raise HTTPException(409, "Asset already archived")

    latest = (
        db.query(Position)
        .filter(Position.asset_id == asset_id)
        .order_by(Position.timestamp.desc(), Position.id.desc())
        .first()
    )
    if latest is not None:
        current_value = value_of_position(db, asset, latest)
        if current_value != 0:
            _, price, _ = compute_value(
                db, asset, 0, latest.currency, latest.accrues_from
            )
            db.add(Position(
                asset_id=asset.id,
                amount=0,
                currency=latest.currency,
                value_in_base=0.0,
                price_used=round(price, 6),
                base_currency=latest.base_currency,
                notes="archived",
                accrues_from=latest.accrues_from,
                flow_in_base=round(-current_value, 4),
            ))

    asset.archived_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/unarchive", response_model=AssetOut)
def unarchive_asset(asset_id: int, db: Session = Depends(get_db)):
    """Bring an archived asset back. Writes no snapshot - the user records a
    fresh amount with Update once it is showing again."""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.archived_at is None:
        raise HTTPException(409, "Asset not archived")
    asset.archived_at = None
    db.commit()
    db.refresh(asset)
    return asset
