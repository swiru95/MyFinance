"""Statistics: portfolio total value over time + allocation breakdown."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asset import Asset
from ..models.position import Position
from .helpers import get_base_currency, latest_positions_by_asset, value_of_position

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/value-over-time")
def value_over_time(db: Session = Depends(get_db)):
    """Reconstruct total portfolio value over time by replaying position history.

    Each position row is a snapshot; we walk them in timestamp order and keep
    a running total (value_in_base is stored per snapshot in the base currency
    that was active at the time).
    """
    base = get_base_currency(db)
    rows = (
        db.query(Position).order_by(Position.timestamp.asc(), Position.id.asc()).all()
    )
    per_asset: dict[int, float] = {}
    points = []
    for r in rows:
        per_asset[r.asset_id] = float(r.value_in_base)
        total = sum(per_asset.values())
        points.append(
            {
                "timestamp": r.timestamp.isoformat(),
                "total": round(total, 2),
            }
        )
    return {"base_currency": base, "points": points}


@router.get("/allocation")
def allocation(db: Session = Depends(get_db)):
    """Current allocation by asset (live-recalculated in base currency)."""
    base = get_base_currency(db)
    assets = {a.id: a for a in db.query(Asset).all()}
    latest = latest_positions_by_asset(db)
    items = []
    total = 0.0
    for asset_id, p in latest.items():
        asset = assets.get(asset_id)
        if not asset:
            continue
        value = value_of_position(db, asset, p)
        total += value
        items.append(
            {
                "asset_id": asset.id,
                "name": asset.name,
                # Fall back to the asset's own name so an uncategorised asset
                # still forms a group of one rather than an unlabelled bucket.
                "category": asset.category or asset.name,
                "icon": asset.icon,
                "kind": asset.kind,
                "units": asset.units,
                "amount": float(p.amount),
                "value": round(value, 2),
            }
        )
    for it in items:
        it["percent"] = round(100.0 * it["value"] / total, 2) if total else 0.0

    # Same numbers rolled up by class. Several assets can share a category
    # (three retirement accounts, three brokers), and that roll-up is what the
    # allocation chart is actually asking about.
    groups: dict[str, dict] = {}
    for it in items:
        g = groups.setdefault(
            it["category"],
            {"category": it["category"], "icon": it["icon"], "value": 0.0, "assets": 0},
        )
        g["value"] += it["value"]
        g["assets"] += 1
    by_category = sorted(groups.values(), key=lambda g: g["value"], reverse=True)
    for g in by_category:
        g["value"] = round(g["value"], 2)
        g["percent"] = round(100.0 * g["value"] / total, 2) if total else 0.0

    return {
        "base_currency": base,
        "total": round(total, 2),
        "items": items,
        "by_category": by_category,
    }
