"""Your money vs growth, per asset and in total.

Every snapshot can carry an optional `flow_in_base` (see
routes/positions.py::_flow_in_base) - what the user paid in or withdrew since
the previous update. This turns that into "how much is mine, how much did the
market/interest add", both for one asset and for the whole portfolio.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..routes.helpers import get_base_currency
from ..models.position import Position


def asset_growth(snapshots: list[Position]) -> dict | None:
    """Growth summary for one asset's full snapshot history.

    None for an empty list - there is nothing to report. Snapshots are
    sorted here (by timestamp, then id to break same-timestamp ties) rather
    than trusted to already be in order, since callers may hand this a group
    straight out of a dict.
    """
    if not snapshots:
        return None
    ordered = sorted(snapshots, key=lambda p: (p.timestamp, p.id))
    later = ordered[1:]

    opening_value = float(ordered[0].value_in_base)
    # Stored None means "not entered" (see routes/positions.py::_flow_in_base);
    # here it counts as nothing added, because leaving the field blank in a
    # month with no deposit is the normal case. untracked_updates says how
    # often that assumption was made.
    contributed = sum(
        float(p.flow_in_base) if p.flow_in_base is not None else 0.0 for p in later
    )
    untracked_updates = sum(1 for p in later if p.flow_in_base is None)
    invested = opening_value + contributed
    value = float(ordered[-1].value_in_base)
    growth = value - invested
    growth_pct = growth / invested if invested > 0 else None

    last = None
    if len(ordered) >= 2:
        previous, latest = ordered[-2], ordered[-1]
        change = float(latest.value_in_base) - float(previous.value_in_base)
        flow = float(latest.flow_in_base) if latest.flow_in_base is not None else None
        last = {
            "change": round(change, 2),
            "flow": None if flow is None else round(flow, 2),
            "growth": round(change - (flow or 0.0), 2),
            "since": previous.timestamp,
            "at": latest.timestamp,
        }

    return {
        "opening_value": round(opening_value, 2),
        "contributed": round(contributed, 2),
        "untracked_updates": untracked_updates,
        "invested": round(invested, 2),
        "value": round(value, 2),
        "growth": round(growth, 2),
        "growth_pct": None if growth_pct is None else round(growth_pct, 4),
        "last": last,
    }


def _totals(assets: list[dict]) -> dict:
    """Sum the per-asset fields; growth_pct is derived, not summed."""
    opening_value = round(sum(a["opening_value"] for a in assets), 2)
    contributed = round(sum(a["contributed"] for a in assets), 2)
    invested = round(sum(a["invested"] for a in assets), 2)
    value = round(sum(a["value"] for a in assets), 2)
    growth = round(sum(a["growth"] for a in assets), 2)
    untracked_updates = sum(a["untracked_updates"] for a in assets)
    growth_pct = growth / invested if invested > 0 else None
    return {
        "opening_value": opening_value,
        "contributed": contributed,
        "invested": invested,
        "value": value,
        "growth": growth,
        "growth_pct": None if growth_pct is None else round(growth_pct, 4),
        "untracked_updates": untracked_updates,
    }


def portfolio_growth(db: Session) -> dict:
    """Growth for every asset plus the portfolio total.

    One query for all positions, grouped by asset in Python, so this costs
    the same single round-trip regardless of how many assets are held.
    """
    rows = (
        db.query(Position)
        .order_by(Position.asset_id, Position.timestamp.asc(), Position.id.asc())
        .all()
    )

    if rows:
        # The most recently written snapshot overall carries the base
        # currency the rest of the app is using right now.
        latest_row = max(rows, key=lambda r: (r.timestamp, r.id))
        base_currency = latest_row.base_currency
    else:
        base_currency = get_base_currency(db)

    grouped: dict[int, list[Position]] = defaultdict(list)
    for row in rows:
        grouped[row.asset_id].append(row)

    assets = []
    for asset_id, snapshots in grouped.items():
        growth = asset_growth(snapshots)
        if growth is None:
            continue
        assets.append({"asset_id": asset_id, **growth})

    return {
        "base_currency": base_currency,
        "assets": assets,
        "total": _totals(assets),
    }
