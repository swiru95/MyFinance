"""The deterministic "next best step" ladder.

Nine standing questions about the wallet, each answered from figures the app
already computes elsewhere (never re-derived here) and reduced to one of a
handful of statuses. This is the ranking material for the `next_steps`
insight - the model orders and explains, it never decides what is done.

Order matters: it is roughly "stop bleeding money" -> "cover the downside"
-> "capture free money" -> "use the tax-advantaged room" -> "plan the long
game" -> "keep the data honest", each rung assuming the ones before it are
at least started.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.settings import Setting
from .budget import month_key, shift_month

RUNG_KEYS = [
    "starter_buffer",
    "envelope_covered",
    "emergency_fund",
    "ppk_on",
    "ikze_used",
    "ike_used",
    "fire_configured",
    "savings_rate_on_track",
    "data_fresh",
]

_FEEDBACK_KEY = "step_feedback"
_LATER_EXPIRY_DAYS = 30


def _rung(key: str, status: str, why_key: str, figures: dict) -> dict:
    order = RUNG_KEYS.index(key)
    return {"key": key, "order": order, "status": status, "figures": figures, "why_key": why_key}


def _safe_total(alloc: dict) -> float:
    band = next((b for b in alloc["by_profile"] if b["profile"] == "safe"), None)
    return band["value"] if band else 0.0


def _active_sources(db: Session, month: str, kind: str) -> list:
    from ..models.income import IncomeSource
    from ..services.income import is_active_in_month

    # `kind` is encrypted, so it is matched here rather than in SQL.
    sources = [s for s in db.query(IncomeSource).all() if s.kind == kind]
    return [s for s in sources if is_active_in_month(s, month)]


def _emergency_target_months(db: Session, has_b2b: bool) -> tuple[float, str]:
    """Months of committed spend the buffer should cover, and where that
    figure came from.

    The default (6 UoP-only / 9 with any B2B active) only applies until the
    person has actually saved FIRE settings - `_load_settings` in
    routes/fire.py hands back a default-valued FireSettings even when
    nothing was ever saved, so the *row* existing (not the value) is what
    marks emergency_months as a deliberate override.
    """
    default = 9.0 if has_b2b else 6.0
    row = db.query(Setting).filter(Setting.key == "fire").first()
    if row and row.value:
        from ..schemas.fire import FireSettings

        settings = FireSettings.model_validate(json.loads(row.value))
        return settings.emergency_months, "fire_settings"
    return default, "default"


def _marginal_rate(db: Session, today: date) -> tuple[float | None, str]:
    """The rate at which one more zloty of this person's income is taxed
    right now, and which schedule it came from.

    Used to price the tax saved by an IKE/IKZE contribution. A B2B source
    wins when both kinds are active: its tax form is a standing choice
    (skala/liniowy/ryczałt), whereas UoP is always skala - so a mixed income
    person's marginal zloty is the one their business earns.
    """
    month = month_key(today)
    b2b_sources = _active_sources(db, month, "b2b")
    uop_sources = _active_sources(db, month, "uop")

    if b2b_sources:
        from ..schemas.income import B2bIncomeParams

        params = B2bIncomeParams.model_validate(b2b_sources[0].params)
        if params.tax_form == "liniowy":
            return 0.19, "liniowy"
        if params.tax_form == "ryczalt":
            return params.ryczalt_rate, "ryczalt"
        return _skala_ytd_rate(db, today, b2b_sources[0], "b2b"), "skala"

    if uop_sources:
        return _skala_ytd_rate(db, today, uop_sources[0], "uop"), "skala"

    return None, "none"


def _skala_ytd_rate(db: Session, today: date, source, kind: str) -> float:
    """12% or 32%, by whether this year's cumulative base has already
    crossed the 120 000 threshold as of the current month.

    Re-runs the same source_year() the income pages use rather than
    re-deriving the schedule, then reads off the one month that matters.
    """
    from ..models.income import IncomeEntry
    from ..routes.helpers import get_base_currency
    from ..services.income import source_year
    from ..services.price_service import PriceService
    from ..tax.pl.params import get_params

    base = get_base_currency(db)
    ps = PriceService(base)
    entries = db.query(IncomeEntry).filter(IncomeEntry.source_id == source.id).all()
    sy = source_year(source, entries, today.year, ps, base)
    current = month_key(today)
    row = next((m for m in sy["months"] if m["month"] == current), None)
    breakdown = row["breakdown"] if row else None
    if not breakdown:
        return 0.12
    if kind == "uop":
        return 0.32 if breakdown.get("over_threshold") else 0.12
    # b2b skala has no over_threshold flag; ytd income vs the threshold does
    # the same job (skala's PIT base is undiscounted income, no health
    # deduction - see tax/pl/b2b.b2b_schedule).
    p = get_params(today.year)
    ytd_income = sum(
        m["breakdown"]["income"]
        for m in sy["months"]
        if m["month"] <= current and m["breakdown"]
    )
    return 0.32 if ytd_income > p.pit_threshold else 0.12


def _wrapper_flows_ytd(db: Session, today: date, wrapper: str) -> float:
    from ..models.asset import Asset
    from ..models.position import Position

    year_start = date(today.year, 1, 1)
    # `wrapper` is encrypted: pick the assets in Python, then their positions by id.
    asset_ids = [a.id for a in db.query(Asset).all() if a.wrapper == wrapper]
    if not asset_ids:
        return 0.0
    rows = db.query(Position).filter(Position.asset_id.in_(asset_ids)).all()
    return sum(
        float(p.flow_in_base)
        for p in rows
        if p.flow_in_base is not None and p.timestamp.date() >= year_start
    )


def build_ladder(db: Session) -> list[dict]:
    from ..routes.expenses import expense_summary
    from ..routes.fire import get_fire
    from ..routes.helpers import get_features, today_in
    from ..routes.income import income_summary
    from ..routes.monthly import analytics as monthly_analytics
    from ..routes.statistics import allocation as allocation_route
    from ..tax.pl.params import get_params

    today = today_in(db)
    month = month_key(today)
    features = get_features(db)

    alloc = allocation_route(db=db)
    expenses_summary = expense_summary(db=db)
    committed = expenses_summary.monthly_total
    business_contributions_total = expenses_summary.business_contributions_total
    safe_total = _safe_total(alloc)
    b2b_active = _active_sources(db, month, "b2b")
    uop_active = _active_sources(db, month, "uop")

    rungs: list[dict] = []

    # 1. starter_buffer - one month of committed spend in safe/cash assets.
    # Needs portfolio for the safe-asset figure; with it off there is nothing
    # to check against, so the rung reads "unknown" rather than guessing from
    # a safe_total that reflects assets nobody is tracking any more.
    if not features.portfolio:
        rungs.append(_rung(
            "starter_buffer", "unknown", "insights.ladder.starter_buffer.why",
            {"note": "portfolio tracking is off - assets are not tracked"},
        ))
    else:
        if safe_total >= committed:
            status = "done"
        elif safe_total > 0:
            status = "in_progress"
        else:
            status = "todo"
        rungs.append(_rung(
            "starter_buffer", status, "insights.ladder.starter_buffer.why",
            {
                "safe_assets": round(safe_total, 2),
                "target": round(committed, 2),
                "business_contributions_total": round(business_contributions_total, 2),
            },
        ))

    # 2. envelope_covered - B2B only: safe assets cover the outstanding
    # ZUS/PIT/VAT set-aside.
    if not b2b_active:
        rungs.append(_rung(
            "envelope_covered", "not_applicable", "insights.ladder.envelope_covered.why",
            {},
        ))
    else:
        outstanding = income_summary(year=today.year, db=db)["envelope_outstanding_in_base"]
        status = "done" if safe_total >= outstanding else "todo"
        rungs.append(_rung(
            "envelope_covered", status, "insights.ladder.envelope_covered.why",
            {"safe_assets": round(safe_total, 2), "envelope_outstanding": outstanding},
        ))

    # 3. emergency_fund - safe assets vs target months of committed spend.
    # Same portfolio dependency as starter_buffer, for the same reason.
    if not features.portfolio:
        rungs.append(_rung(
            "emergency_fund", "unknown", "insights.ladder.emergency_fund.why",
            {"note": "portfolio tracking is off - assets are not tracked"},
        ))
    else:
        target_months, target_source = _emergency_target_months(db, bool(b2b_active))
        required = target_months * committed
        if safe_total >= required:
            status = "done"
        elif safe_total > 0:
            status = "in_progress"
        else:
            status = "todo"
        rungs.append(_rung(
            "emergency_fund", status, "insights.ladder.emergency_fund.why",
            {
                "safe_assets": round(safe_total, 2),
                "target_months": target_months,
                "target_source": target_source,
                "required": round(required, 2),
                "business_contributions_total": round(business_contributions_total, 2),
            },
        ))

    # 4. ppk_on - an active UoP source contributing to PPK.
    if not uop_active:
        rungs.append(_rung("ppk_on", "not_applicable", "insights.ladder.ppk_on.why", {}))
    else:
        from ..schemas.income import UopIncomeParams

        params = UopIncomeParams.model_validate(uop_active[0].params)
        status = "done" if params.ppk_employee > 0 else "todo"
        rungs.append(_rung(
            "ppk_on", status, "insights.ladder.ppk_on.why",
            {"ppk_employee": params.ppk_employee, "ppk_employer": params.ppk_employer},
        ))

    # 5/6. ikze_used / ike_used - this year's flows into each wrapper vs its
    # annual limit. IKZE also carries the tax the contribution saved at the
    # marginal rate (it is a straight PIT deduction); IKE's benefit is a
    # future Belka exemption, not a deduction against this year's income, so
    # no marginal-rate figure is attached to it.
    params = get_params(today.year)
    marginal_rate, rate_source = _marginal_rate(db, today)
    for wrapper in ("ikze", "ike"):
        key = f"{wrapper}_used"
        # Both wrappers are read entirely off position flows into IKZE/IKE
        # assets - with portfolio off there are no flows to read.
        if not features.portfolio:
            rungs.append(_rung(key, "not_applicable", f"insights.ladder.{key}.why", {}))
            continue
        flows = _wrapper_flows_ytd(db, today, wrapper)
        limit = (
            (params.ikze_limit_jdg if b2b_active else params.ikze_limit)
            if wrapper == "ikze"
            else params.ike_limit
        )
        if flows >= limit:
            status = "done"
        elif flows > 0:
            status = "in_progress"
        else:
            status = "todo"
        figures = {"flows_ytd": round(flows, 2), "limit": limit}
        if wrapper == "ikze":
            figures["marginal_rate"] = marginal_rate
            figures["marginal_rate_source"] = rate_source
            figures["tax_saved"] = (
                round(flows * marginal_rate, 2) if marginal_rate is not None else None
            )
        rungs.append(_rung(key, status, f"insights.ladder.{key}.why", figures))

    # 7/8. fire_configured, savings_rate_on_track - both read the FIRE
    # projection, so both go "not_applicable" together when the feature (and
    # therefore portfolio, its dependency) is off.
    if not features.fire:
        rungs.append(_rung(
            "fire_configured", "not_applicable", "insights.ladder.fire_configured.why", {},
        ))
        rungs.append(_rung(
            "savings_rate_on_track", "not_applicable",
            "insights.ladder.savings_rate_on_track.why", {},
        ))
    else:
        fire_payload = get_fire(db=db)
        fire_settings = fire_payload["settings"]
        configured = (
            fire_settings.birth_year is not None and fire_settings.target_fi_age is not None
        )
        rungs.append(_rung(
            "fire_configured", "done" if configured else "todo",
            "insights.ladder.fire_configured.why",
            {
                "birth_year": fire_settings.birth_year,
                "target_fi_age": fire_settings.target_fi_age,
            },
        ))

        result = fire_payload.get("result")
        required_block = result.get("required") if result else None
        if not configured or required_block is None:
            rungs.append(_rung(
                "savings_rate_on_track", "unknown",
                "insights.ladder.savings_rate_on_track.why", {},
            ))
        else:
            current_rate = result.get("current_savings_rate")
            required_rate = required_block.get("savings_rate")
            if current_rate is None or required_rate is None:
                status = "unknown"
            else:
                status = "done" if current_rate >= required_rate else "todo"
            rungs.append(_rung(
                "savings_rate_on_track", status, "insights.ladder.savings_rate_on_track.why",
                {"current_savings_rate": current_rate, "required_savings_rate": required_rate},
            ))

    # 9. data_fresh - every non-illiquid asset snapshotted recently, and the
    # last two completed months have typed spending.
    from ..models.asset import Asset
    from ..models.monthly import MonthlyRecord
    from ..profiles import for_category

    # The staleness half needs portfolio (it is asset snapshots); the
    # recorded-months half does not, so only that half runs with it off
    # rather than marking the whole rung not_applicable.
    if features.portfolio:
        relevant = [
            a for a in db.query(Asset).all()
            if a.archived_at is None
            and (a.profile or for_category(a.category)) != "illiquid"
        ]
        latest = _latest_positions(db)
        cutoff = today - timedelta(days=45)
        stale = [
            a.name for a in relevant
            if a.id not in latest or latest[a.id].timestamp.date() < cutoff
        ]
    else:
        relevant, stale = [], []
    completed_months = [shift_month(month, -1), shift_month(month, -2)]
    recorded_months = {
        r.month for r in db.query(MonthlyRecord).filter(MonthlyRecord.month.in_(completed_months)).all()
    }
    missing_months = [m for m in completed_months if m not in recorded_months]
    if not stale and not missing_months:
        status = "done"
    elif len(stale) == len(relevant) and len(missing_months) == len(completed_months):
        status = "todo"
    else:
        status = "in_progress"
    rungs.append(_rung(
        "data_fresh", status, "insights.ladder.data_fresh.why",
        {"stale_assets": stale, "missing_months": missing_months},
    ))

    feedback = active_feedback(db)
    for r in rungs:
        r["feedback"] = feedback.get(r["key"])
    return rungs


def _latest_positions(db: Session) -> dict:
    from ..routes.helpers import latest_positions_by_asset

    return latest_positions_by_asset(db)


def load_feedback(db: Session) -> dict:
    row = db.query(Setting).filter(Setting.key == _FEEDBACK_KEY).first()
    if not row or not row.value:
        return {}
    return json.loads(row.value)


def save_feedback_entry(db: Session, key: str, state: str) -> dict:
    from datetime import datetime, timezone

    feedback = load_feedback(db)
    feedback[key] = {"state": state, "at": datetime.now(timezone.utc).isoformat()}
    row = db.query(Setting).filter(Setting.key == _FEEDBACK_KEY).first()
    payload = json.dumps(feedback)
    if row is None:
        db.add(Setting(key=_FEEDBACK_KEY, value=payload))
    else:
        row.value = payload
    db.commit()
    return feedback[key]


def active_feedback(db: Session) -> dict:
    """Stored feedback, dropping any "later" entry past its 30-day expiry.

    "done" and "dismissed" are standing decisions and never expire; "later"
    is a snooze, not a decision, so it lapses back into a visible todo.
    """
    from datetime import datetime, timezone

    feedback = load_feedback(db)
    now = datetime.now(timezone.utc)
    out = {}
    for key, entry in feedback.items():
        if entry.get("state") == "later":
            try:
                at = datetime.fromisoformat(entry["at"])
            except (KeyError, ValueError):
                continue
            if now - at > timedelta(days=_LATER_EXPIRY_DAYS):
                continue
        out[key] = entry
    return out
