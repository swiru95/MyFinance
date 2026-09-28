"""Your money vs growth, per asset and in total.

Every snapshot can carry an optional `flow_in_base` (see
routes/positions.py::_flow_in_base) - what the user paid in or withdrew since
the previous update. This turns that into "how much is mine, how much did the
market/interest add", both for one asset and for the whole portfolio.

`value` (and everything derived from it - `growth`, `growth_pct`, the totals)
is revalued at today's prices via routes/helpers.py::value_of_position,
matching /api/summary, rather than trusting the latest snapshot's stored
`value_in_base` - a stored snapshot is only as fresh as the last time the
user touched that asset, so a crypto/metal holding left untouched for weeks
would otherwise disagree with the dashboard total. `last` (the latest update
vs. the one before) is the exception: it describes that update as recorded,
so it stays on stored snapshot values.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from ..routes.helpers import get_base_currency, value_of_position
from ..models.asset import Asset
from ..models.position import Position


def asset_growth(snapshots: list[Position], current_value: float | None = None) -> dict | None:
    """Growth summary for one asset's full snapshot history.

    None for an empty list - there is nothing to report. Snapshots are
    sorted here (by timestamp, then id to break same-timestamp ties) rather
    than trusted to already be in order, since callers may hand this a group
    straight out of a dict.

    `current_value` overrides the latest snapshot's stored `value_in_base`
    when given (portfolio_growth passes today's live-priced value; callers
    that only have snapshots on hand - e.g. tests - can leave it out and get
    the stored figure back).
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
    value = float(ordered[-1].value_in_base) if current_value is None else current_value
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


def _totals(assets: list[dict], value_raw: float | None = None) -> dict:
    """Sum the per-asset fields; growth_pct is derived, not summed.

    `value_raw` is the unrounded sum of current values. Summing it before
    rounding (as /api/summary does) keeps "Value now" equal to the
    dashboard total to the grosz; summing per-asset figures already rounded
    to 2 dp can drift by one. Growth is then value - invested, so the three
    summary figures always add up on screen.
    """
    opening_value = round(sum(a["opening_value"] for a in assets), 2)
    contributed = round(sum(a["contributed"] for a in assets), 2)
    invested = round(sum(a["invested"] for a in assets), 2)
    value = round(value_raw if value_raw is not None else sum(a["value"] for a in assets), 2)
    growth = round(value - invested, 2)
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
    Assets are loaded once up front and reused for every value_of_position
    call rather than queried per asset.
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

    assets_by_id = {a.id: a for a in db.query(Asset).all()}

    grouped: dict[int, list[Position]] = defaultdict(list)
    for row in rows:
        grouped[row.asset_id].append(row)

    assets = []
    value_raw = 0.0
    for asset_id, snapshots in grouped.items():
        asset = assets_by_id.get(asset_id)
        if asset is None:
            # The asset was deleted after these snapshots were written -
            # nothing left to reprice against.
            continue
        latest = max(snapshots, key=lambda p: (p.timestamp, p.id))
        current_value = value_of_position(db, asset, latest)
        growth = asset_growth(snapshots, current_value=current_value)
        if growth is None:
            continue
        value_raw += current_value
        assets.append({
            "asset_id": asset_id,
            "archived": asset.archived_at is not None,
            **growth,
        })

    return {
        "base_currency": base_currency,
        "assets": assets,
        "total": _totals(assets, value_raw),
    }
