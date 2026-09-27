"""Income source maths: turn a recurring source's monthly figures into a
year run through the matching Polish tax schedule, and combine every
source's contribution across a set of months.

A source is like a recurring expense: `params` hold the default monthly
figures, they apply between `starts_on` and `ends_on`, and an `IncomeEntry`
overrides exactly one month (a bonus, an unpaid month, a different invoice).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models.income import IncomeEntry, IncomeSource
from ..schemas.income import PARAM_MODELS
from ..services.price_service import PriceService
from ..tax.pl.b2b import b2b_schedule
from ..tax.pl.calendar import working_days as calendar_working_days
from ..tax.pl.calendar import working_hours as calendar_working_hours
from ..tax.pl.params import EARLIEST_YEAR, money
from ..tax.pl.uop import uop_schedule


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return first, last


def is_active_in_month(src: IncomeSource, month: str) -> bool:
    """Whether `src`'s [starts_on, ends_on] range overlaps `month` at all."""
    year, mon = int(month[:4]), int(month[5:7])
    first, last = _month_bounds(year, mon)
    return first <= (src.ends_on or date.max) and last >= src.starts_on


def _convert(ps: PriceService, amount: float, currency: str, to: str) -> float:
    """`amount` in `currency` converted to `to`.

    Imported lazily: routes/__init__ pulls in routes.monthly, whose schemas
    import services.budget, so a top-level import of routes.helpers here
    would be circular whenever this module is imported before that chain
    finishes (see services/budget.py's convert_currency import for the same
    issue, and 00-architecture.md's note on it).
    """
    from ..routes.helpers import convert_currency

    return convert_currency(ps, amount, currency, to)


def source_year(
    src: IncomeSource, entries: list[IncomeEntry], year: int, ps: PriceService, base: str
) -> dict:
    """One source's 12 months for `year`, run through its matching PL tax
    schedule.

    The engine only understands PLN, so a non-PLN source is converted at
    *today's* rate before the schedule runs - the law actually uses the NBP
    reference rate from the day before each invoice, which would require
    every past month to be priced at its own historical rate. Good enough
    for planning, not for a tax return.
    """
    by_month = {e.month: e for e in entries}
    kind = src.kind
    params_model = PARAM_MODELS[kind].model_validate(src.params)
    # Only a daily/hourly b2b source has a working-time calendar behind it;
    # every other kind/billing leaves units/units_source as None throughout.
    is_day_hour_b2b = kind == "b2b" and params_model.billing in ("daily", "hourly")

    months_str: list[str] = []
    amounts_raw: list[float] = []
    costs_raw: list[float] = []
    actives: list[bool] = []
    has_entries: list[bool] = []
    overrides: list[float | None] = []
    units_list: list[float | None] = []
    units_source_list: list[str | None] = []
    calendar_days_list: list[int | None] = []
    calendar_hours_list: list[int | None] = []

    for i in range(12):
        month_num = i + 1
        month_str = f"{year:04d}-{month_num:02d}"
        active = is_active_in_month(src, month_str)
        entry = by_month.get(month_str)
        has_entry = entry is not None

        cal_days = cal_hours = None
        if is_day_hour_b2b:
            # Reference figures shown alongside the month regardless of
            # active/entry state - "what the calendar says this month is".
            cal_days = calendar_working_days(year, month_num)
            cal_hours = calendar_working_hours(year, month_num)
        calendar_units = (
            cal_days if params_model.billing == "daily" else cal_hours
        ) if is_day_hour_b2b else None

        units: float | None = None
        units_source: str | None = None

        if has_entry:
            amount = float(entry.amount)
            costs = float(entry.costs)
            override_net = (
                float(entry.override_net) if entry.override_net is not None else None
            )
            if is_day_hour_b2b and entry.units is not None:
                units, units_source = float(entry.units), "entry"
        elif active:
            if kind == "uop":
                amount = params_model.gross_monthly
            elif kind == "b2b":
                amount = params_model.default_revenue_monthly(calendar_units)
            else:
                amount = params_model.net_monthly
            costs = params_model.costs_monthly if kind == "b2b" else 0.0
            override_net = None
            if is_day_hour_b2b:
                if params_model.units_per_month is not None:
                    units, units_source = params_model.units_per_month, "fixed"
                else:
                    units, units_source = calendar_units, "calendar"
        else:
            amount, costs, override_net = 0.0, 0.0, None

        months_str.append(month_str)
        amounts_raw.append(amount)
        costs_raw.append(costs)
        actives.append(active)
        has_entries.append(has_entry)
        overrides.append(override_net)
        units_list.append(units)
        units_source_list.append(units_source)
        calendar_days_list.append(cal_days)
        calendar_hours_list.append(cal_hours)

    amounts_pln = [_convert(ps, a, src.currency, "PLN") for a in amounts_raw]
    costs_pln = [_convert(ps, c, src.currency, "PLN") for c in costs_raw]

    schedule = None
    breakdowns: list[dict | None] = [None] * 12
    if kind == "uop":
        schedule = uop_schedule(year, amounts_pln, params_model.to_options())
        breakdowns = [m.to_dict() for m in schedule.months]
    elif kind == "b2b":
        schedule = b2b_schedule(
            year, amounts_pln, costs_pln, params_model.to_options(), active_by_month=actives
        )
        breakdowns = [m.to_dict() for m in schedule.months]

    months: list[dict] = []
    total_amount = total_net_pln = total_net_in_base = 0.0
    for i in range(12):
        override_net = overrides[i]
        breakdown = breakdowns[i]
        if override_net is not None:
            net_pln = _convert(ps, override_net, src.currency, "PLN")
        elif kind == "uop":
            net_pln = breakdown["net"]
        elif kind == "b2b":
            net_pln = breakdown["take_home"]
        else:
            net_pln = amounts_pln[i]
        net_in_base = _convert(ps, net_pln, "PLN", base)

        row = {
            "month": months_str[i],
            "active": actives[i],
            "has_entry": has_entries[i],
            "amount": money(amounts_raw[i]),
            "overridden": override_net is not None,
            "breakdown": breakdown,
            "net_pln": money(net_pln),
            "net_in_base": money(net_in_base),
        }
        if kind == "uop" and breakdown is not None:
            row["employer_cost"] = breakdown["employer_cost"]
        if kind == "b2b" and breakdown is not None:
            row["set_aside"] = breakdown["set_aside"]
            row["vat_due"] = breakdown["vat_due"]
        # Present on every month regardless of kind, None unless this is a
        # day/hour-billed b2b source - a uniform shape the frontend can rely
        # on without branching on `kind` first.
        row["units"] = units_list[i]
        row["units_source"] = units_source_list[i]
        row["working_days"] = calendar_days_list[i]
        row["working_hours"] = calendar_hours_list[i]
        months.append(row)

        total_amount += amounts_raw[i]
        total_net_pln += net_pln
        total_net_in_base += net_in_base

    result: dict = {
        "source_id": src.id,
        "name": src.name,
        "kind": kind,
        "currency": src.currency,
        "year": year,
        "months": months,
    }
    if schedule is not None:
        schedule_dict = schedule.to_dict()
        schedule_dict.pop("months", None)
        result.update(schedule_dict)
    else:
        # "other" has no tax maths, so the only "year summary" it can offer
        # is a plain sum of what source_year already computed per month.
        result["totals"] = {
            "amount": money(total_amount),
            "net_pln": money(total_net_pln),
            "net_in_base": money(total_net_in_base),
        }
    return result


def income_by_month(
    db: Session, months: list[str], ps: PriceService, base: str
) -> dict[str, dict]:
    """Every source's contribution to each of `months`.

    Groups the requested months by calendar year and computes each source's
    year once, so a two-year span costs at most two schedule runs per
    source rather than one per month. Sources with no active month and no
    entry in a given month contribute nothing to it.
    """
    if not months:
        return {}

    sources = db.query(IncomeSource).all()
    if not sources:
        return {m: {"total_in_base": 0.0, "sources": [], "rules_missing": False} for m in months}

    entries_by_source: dict[int, list[IncomeEntry]] = {}
    for e in db.query(IncomeEntry).all():
        entries_by_source.setdefault(e.source_id, []).append(e)

    # Years without tax rules are skipped, not approximated; see EARLIEST_YEAR.
    years = sorted({int(m[:4]) for m in months if int(m[:4]) >= EARLIEST_YEAR})
    by_source_month: dict[int, dict[str, dict]] = {}
    for src in sources:
        entries = entries_by_source.get(src.id, [])
        merged: dict[str, dict] = {}
        for year in years:
            sy = source_year(src, entries, year, ps, base)
            merged.update({row["month"]: row for row in sy["months"]})
        by_source_month[src.id] = merged

    result: dict[str, dict] = {}
    for m in months:
        total = 0.0
        rows = []
        for src in sources:
            row = by_source_month[src.id].get(m)
            if row is None or not (row["active"] or row["has_entry"]):
                continue
            total += row["net_in_base"]
            rows.append(
                {
                    "source_id": src.id,
                    "name": src.name,
                    "kind": src.kind,
                    "net_in_base": row["net_in_base"],
                    "overridden": row["overridden"],
                }
            )
        result[m] = {
            "total_in_base": money(total),
            "sources": rows,
            "rules_missing": int(m[:4]) < EARLIEST_YEAR,
        }
    return result
