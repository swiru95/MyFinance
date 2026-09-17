"""Statistics: portfolio total value over time + allocation breakdown."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.asset import Asset
from ..models.position import Position
from .helpers import (
    get_base_currency,
    latest_positions_by_asset,
    today_in,
    value_of_position,
)

# One slot is kept for the folded tail, so seven series get their own hue.
MAX_SERIES = 8
OTHER_KEY = "__other__"

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/value-over-time")
def value_over_time(by: str = "total", db: Session = Depends(get_db)):
    """Portfolio value per day, optionally split into series.

    `by` is one of total | asset | category | profile.

    The previous implementation emitted one point per position *row*, so
    importing twenty-one holdings in one sitting drew a twenty-one step ramp
    from zero - that was the insertion order of the rows, not the history of
    the portfolio. Days are the unit here: for each day, each asset
    contributes its most recent snapshot as of that day, and nothing
    contributes before its first snapshot exists.

    value_in_base is the figure computed when the snapshot was taken, so past
    points keep the prices of their own day rather than being revalued at
    today's.
    """
    from datetime import timedelta

    from ..profiles import for_category

    base = get_base_currency(db)
    mode = by if by in {"total", "asset", "category", "profile"} else "total"

    rows = (
        db.query(Position).order_by(Position.timestamp.asc(), Position.id.asc()).all()
    )
    if not rows:
        return {"base_currency": base, "mode": mode, "keys": [], "rows": []}

    assets = {a.id: a for a in db.query(Asset).all()}

    def series_key(asset: Asset) -> tuple[str, str]:
        if mode == "asset":
            return (f"asset-{asset.id}", asset.name)
        if mode == "category":
            name = asset.category or asset.name
            return (name, name)
        if mode == "profile":
            name = asset.profile or for_category(asset.category)
            return (name, name)
        return ("total", "total")

    first = rows[0].timestamp.date()
    last = max(today_in(db), rows[-1].timestamp.date())
    # A snapshot taken today is the whole history when the app is new; one
    # point still renders as a dot, so no special case is needed here.
    days = []
    day = first
    while day <= last:
        days.append(day)
        day += timedelta(days=1)

    # asset_id -> value as of the day being walked, carried forward
    latest: dict[int, float] = {}
    cursor = 0
    out_rows = []
    totals: dict[str, float] = {}
    for day in days:
        while cursor < len(rows) and rows[cursor].timestamp.date() <= day:
            latest[rows[cursor].asset_id] = float(rows[cursor].value_in_base)
            cursor += 1
        buckets: dict[str, float] = {}
        for asset_id, value in latest.items():
            asset = assets.get(asset_id)
            if not asset:
                continue
            key, _ = series_key(asset)
            buckets[key] = buckets.get(key, 0.0) + value
        for key, value in buckets.items():
            totals[key] = max(totals.get(key, 0.0), value)
        out_rows.append({
            "date": day.isoformat(),
            "total": round(sum(buckets.values()), 2),
            **{k: round(v, 2) for k, v in buckets.items()},
        })

    if mode == "total":
        return {
            "base_currency": base,
            "mode": mode,
            "keys": [{"key": "total", "label": "total"}],
            "rows": out_rows,
        }

    # The palette has a fixed number of hues and they are never cycled, so the
    # tail folds into one "Other" series rather than repeating a colour. Rank
    # by each series' peak, so something that mattered once is not hidden by
    # having since been sold down.
    labels = {}
    for asset in assets.values():
        key, label = series_key(asset)
        labels[key] = label
    if mode == "profile":
        # Bands have a canonical order and a hue must stay with its band, so
        # these are never ranked by size the way assets and classes are.
        from ..profiles import BANDS

        ranked = [b for b in BANDS if b in totals]
    else:
        ranked = sorted(totals, key=lambda k: totals[k], reverse=True)
    head, tail = ranked[:MAX_SERIES - 1], ranked[MAX_SERIES - 1:]
    if tail:
        for row in out_rows:
            folded = sum(row.pop(k, 0.0) for k in tail)
            if folded:
                row[OTHER_KEY] = round(folded, 2)
        for row in out_rows:
            row.setdefault(OTHER_KEY, 0.0)

    keys = [{"key": k, "label": labels.get(k, k)} for k in head]
    if tail:
        keys.append({
            "key": OTHER_KEY,
            "label": OTHER_KEY,
            "members": [labels.get(k, k) for k in tail],
        })
    return {"base_currency": base, "mode": mode, "keys": keys, "rows": out_rows}


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
                "profile": asset.profile or "",
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

    # And once more by risk band. Ordered deliberately - safest first - so the
    # chart reads left to right as exposure increases rather than by size.
    from ..profiles import BANDS, for_category

    bands: dict[str, dict] = {}
    for it in items:
        key = it["profile"] or for_category(it["category"])
        b = bands.setdefault(key, {"profile": key, "value": 0.0, "categories": set()})
        b["value"] += it["value"]
        b["categories"].add(it["category"])
    by_profile = []
    for name in BANDS:
        b = bands.get(name)
        if not b:
            continue
        by_profile.append({
            "profile": name,
            "value": round(b["value"], 2),
            "percent": round(100.0 * b["value"] / total, 2) if total else 0.0,
            "categories": sorted(b["categories"]),
        })

    return {
        "base_currency": base,
        "total": round(total, 2),
        "items": items,
        "by_category": by_category,
        "by_profile": by_profile,
    }
