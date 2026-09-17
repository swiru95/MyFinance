"""Portfolio value as of a past date.

The month pages need to ask "what was the whole portfolio worth on this day",
which is a different question from "what is it worth now" that the allocation
endpoint answers. Both are derived from the same position snapshots; only the
as-of date differs.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..models.position import Position


def wallet_values(db: Session, days: list[date]) -> dict[date, float | None]:
    """Portfolio value in base currency at the end of each requested day.

    Each asset contributes its most recent snapshot as of that day, carried
    forward until the next one - the same rule the value-over-time chart
    follows, so the two never disagree.

    `value_in_base` is the figure computed when the snapshot was taken, so a
    past day keeps the prices of its own day rather than being revalued at
    today's. That is what makes a month-on-month difference meaningful: it
    reflects what the portfolio did, not what today's gold price would have
    made of it.

    A day earlier than the first snapshot maps to None, never 0.0. An empty
    history means the value is unknown, and treating unknown as zero would
    invent a portfolio-sized gain in the first month the app is used.
    """
    if not days:
        return {}

    rows = (
        db.query(Position)
        .order_by(Position.timestamp.asc(), Position.id.asc())
        .all()
    )
    out: dict[date, float | None] = {}
    if not rows:
        return {d: None for d in days}

    first_snapshot = rows[0].timestamp.date()
    # One ordered walk over the snapshots serves every requested day, so asking
    # for two years of month boundaries costs the same scan as asking for one.
    latest: dict[int, float] = {}
    cursor = 0
    for day in sorted(set(days)):
        if day < first_snapshot:
            out[day] = None
            continue
        while cursor < len(rows) and rows[cursor].timestamp.date() <= day:
            latest[rows[cursor].asset_id] = float(rows[cursor].value_in_base)
            cursor += 1
        out[day] = round(sum(latest.values()), 2)
    return out
