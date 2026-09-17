"""Asset type endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asset import Asset
from ..schemas.asset import AssetIn, AssetOut

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


@router.delete("/{asset_id}", status_code=204)
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    from ..models.position import Position

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        from fastapi import HTTPException

        raise HTTPException(404, "Asset not found")
    db.query(Position).filter(Position.asset_id == asset_id).delete()
    db.delete(asset)
    db.commit()
