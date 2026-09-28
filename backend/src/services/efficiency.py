"""Efficiency ("your money vs growth") scoped to one reporting period, plus
the total portfolio's annualised (XIRR) return - the numbers behind the PDF
report's efficiency section (see services/wallet_report.py).

Reuses services/growth.py's asset_growth/portfolio_growth rather than
recomputing deposits-vs-growth a second way: `since` just tells that
existing code which snapshots belong to this period's own activity versus
the value the asset was already carrying in at the period's start. The
Assets page and the PDF can never quietly disagree about what "your money"
and "growth" mean.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from ..models.asset import Asset
from ..models.position import Position
from .growth import portfolio_growth
from .xirr import xirr

# Short enough to fit the `insights.period` column (String(7), shared with
# the "YYYY-MM" a digest stores there - see schemas/insight.py).
PERIODS = ("1m", "3m", "ytd", "12m", "all")

PERIOD_LABELS = {
    "1m": "Last month",
    "3m": "Last quarter",
    "ytd": "Year to date",
    "12m": "Last 12 months",
    "all": "All time",
}


def _subtract_months(d: date, months: int) -> date:
    """`d` minus a whole number of calendar months, with the day clamped to
    the target month's actual length (Aug 31 minus 6 months lands on Feb 28
    or 29, never rolls over into March)."""
    month_index = d.month - 1 - months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def period_start(period: str, today: date) -> date | None:
    """The last day still treated as "before" `period` - the `since` cutoff
    asset_growth/portfolio_growth take. None means all time (no cutoff)."""
    if period == "1m":
        return _subtract_months(today, 1)
    if period == "3m":
        return _subtract_months(today, 3)
    if period == "ytd":
        return date(today.year - 1, 12, 31)
    if period == "12m":
        return _subtract_months(today, 12)
    return None


def _cashflows(db: Session, since: date | None, today: date) -> list[tuple[date, float]]:
    """One dated cash flow per asset: an opening outflow (the value it
    already carried in at the period's start, or its first-ever snapshot
    when it is newer than the period), an outflow for every deposit and an
    inflow for every withdrawal recorded inside the period, and one closing
    inflow for today's live total - exactly the same deposits/withdrawals
    portfolio_growth's `since` isolates, just kept as individual dated
    entries instead of summed, which is what xirr() needs to solve for an
    annualised rate.
    """
    from ..routes.helpers import value_of_position

    rows = (
        db.query(Position)
        .order_by(Position.asset_id, Position.timestamp.asc(), Position.id.asc())
        .all()
    )
    assets = {a.id: a for a in db.query(Asset).all()}
    grouped: dict[int, list[Position]] = defaultdict(list)
    for row in rows:
        grouped[row.asset_id].append(row)

    flows: list[tuple[date, float]] = []
    total_current = 0.0
    for asset_id, snapshots in grouped.items():
        asset = assets.get(asset_id)
        if asset is None:
            continue
        ordered = sorted(snapshots, key=lambda p: (p.timestamp, p.id))
        before = [p for p in ordered if since is not None and p.timestamp.date() <= since]
        after = [p for p in ordered if since is None or p.timestamp.date() > since]

        if before:
            flows.append((since, -float(before[-1].value_in_base)))
            later = after
        elif after:
            flows.append((after[0].timestamp.date(), -float(after[0].value_in_base)))
            later = after[1:]
        else:  # pragma: no cover - unreachable, every asset has >=1 snapshot
            later = []

        for p in later:
            if p.flow_in_base:
                flows.append((p.timestamp.date(), -float(p.flow_in_base)))

        latest = ordered[-1]
        total_current += value_of_position(db, asset, latest)

    if total_current:
        flows.append((today, total_current))
    return flows


def period_efficiency(db: Session, period: str, today: date) -> dict:
    """Deposits vs growth for every asset and the total, scoped to `period`,
    plus the total's annualised (XIRR) return."""
    since = period_start(period, today)
    growth = portfolio_growth(db, since=since)

    assets = {a.id: a for a in db.query(Asset).all()}
    for row in growth["assets"]:
        asset = assets.get(row["asset_id"])
        row["name"] = asset.name if asset else ""
        row["category"] = (asset.category or asset.name) if asset else ""
        row["wrapper"] = (asset.wrapper or "") if asset else ""
        # "last" (the latest update vs. the one before) carries two raw
        # datetime objects - fine for /api/positions/growth, whose FastAPI
        # response model knows how to serialize those, but this dict is
        # also stored straight into a JSON column (Insight.snapshot) via
        # plain json.dumps, which does not. Nothing here reads "last" - the
        # report describes the whole period, not one update - so it is
        # dropped rather than reformatted.
        row.pop("last", None)

    cashflows = _cashflows(db, since, today)
    annualized_return = xirr(cashflows)

    return {
        "period": period,
        "period_label": PERIOD_LABELS.get(period, period),
        "since": since.isoformat() if since else None,
        "until": today.isoformat(),
        "base_currency": growth["base_currency"],
        "assets": growth["assets"],
        "total": growth["total"],
        "annualized_return": None if annualized_return is None else round(annualized_return, 4),
    }
