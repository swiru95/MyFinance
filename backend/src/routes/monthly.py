"""Monthly budget + analytics endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.expense import Expense
from ..models.income import IncomeSource
from ..models.monthly import MonthlyRecord
from ..schemas.monthly import (
    MonthlyAnalytics,
    MonthlyIn,
    MonthlyOut,
    MonthlyPatch,
    TimelinePoint,
)
from ..services.budget import (
    MONTH_RE,
    committed_for_month,
    effective_spend,
    month_key,
    shift_month,
    wallet_window,
)
from ..services.income import income_by_month, is_active_in_month
from ..tax.pl.params import EARLIEST_YEAR
from ..services.portfolio import wallet_values
from ..services.price_service import PriceService
from .helpers import convert_currency, get_base_currency, today_in

router = APIRouter(prefix="/api/monthly", tags=["monthly"])

import re

_MONTH_PATTERN = re.compile(MONTH_RE)


def _validate_month(month: str) -> str:
    if not _MONTH_PATTERN.match(month):
        raise HTTPException(422, "month must be in YYYY-MM form")
    return month


def _wallet_for_months(
    db: Session, months: list[str], today: date
) -> dict[str, tuple[float | None, float | None]]:
    """Opening and closing portfolio value for each month, in one scan.

    The two boundary days of every month are collected first and priced
    together, so a two-year analytics span walks the snapshot history once
    rather than once per month.
    """
    windows = {m: wallet_window(m, today) for m in months}
    days = [d for w in windows.values() if w for d in w]
    values = wallet_values(db, days)
    return {
        m: (values.get(w[0]), values.get(w[1])) if w else (None, None)
        for m, w in windows.items()
    }


def _build(
    month: str,
    record: MonthlyRecord | None,
    expenses: list[Expense],
    ps: PriceService,
    base: str,
    wallet: tuple[float | None, float | None] = (None, None),
    source_income: dict | None = None,
) -> MonthlyOut:
    committed, by_cat = committed_for_month(expenses, month, ps, base)
    currency = record.currency if record else base
    income = float(record.income) if record else 0.0
    actual = float(record.actual_spent) if record else 0.0
    income_base_typed = convert_currency(ps, income, currency, base)
    actual_base = convert_currency(ps, actual, currency, base)

    source_income = source_income or {"total_in_base": 0.0, "sources": []}
    income_from_sources = source_income["total_in_base"]
    income_total = income_base_typed + income_from_sources

    surplus = income_total - actual_base
    wallet_start, wallet_end = wallet
    change = (
        round(wallet_end - wallet_start, 2)
        if wallet_start is not None and wallet_end is not None
        else None
    )
    effective = effective_spend(income_total, wallet_start, wallet_end)
    return MonthlyOut(
        month=month,
        income=income,
        actual_spent=actual,
        currency=currency,
        notes=record.notes if record else "",
        base_currency=base,
        income_in_base=round(income_total, 2),
        income_from_sources_in_base=round(income_from_sources, 2),
        income_sources=source_income["sources"],
        actual_in_base=round(actual_base, 2),
        committed=round(committed, 2),
        surplus=round(surplus, 2),
        savings_rate=round(100.0 * surplus / income_total, 1) if income_total else None,
        variance=round(actual_base - committed, 2),
        wallet_start=wallet_start,
        wallet_end=wallet_end,
        wallet_change=change,
        effective_spent=round(effective, 2) if effective is not None else None,
        by_category=sorted(
            ({"category": k, "total": round(v, 2)} for k, v in by_cat.items()),
            key=lambda d: d["total"],
            reverse=True,
        ),
        saved=record is not None,
        updated_at=record.updated_at if record else None,
    )


@router.get("", response_model=list[MonthlyOut])
def list_months(db: Session = Depends(get_db)):
    """Saved months, newest first, with the current month always present.

    Also includes every month an income source is active in, back to at most
    23 months before the current one - a source with no saved MonthlyRecord
    still needs a row to appear on, or its income would exist only inside
    the /api/income endpoints and never surface on the budget page.
    """
    base = get_base_currency(db)
    ps = PriceService(base)
    expenses = db.query(Expense).all()
    records = {r.month: r for r in db.query(MonthlyRecord).all()}
    today = today_in(db)
    current = month_key(today)

    candidate_months = set(records) | {current}
    sources = db.query(IncomeSource).all()
    if sources:
        earliest = min(s.starts_on for s in sources)
        span_start = max(
            month_key(earliest), shift_month(current, -23), f"{EARLIEST_YEAR}-01"
        )
        m = span_start
        while m <= current:
            if any(is_active_in_month(s, m) for s in sources):
                candidate_months.add(m)
            m = shift_month(m, 1)

    months = sorted(candidate_months, reverse=True)
    wallet = _wallet_for_months(db, months, today)
    source_income = income_by_month(db, months, ps, base)
    return [
        _build(m, records.get(m), expenses, ps, base, wallet[m], source_income.get(m))
        for m in months
    ]


@router.get("/analytics", response_model=MonthlyAnalytics)
def analytics(
    months_back: int = Query(11, ge=0, le=60),
    months_ahead: int = Query(12, ge=0, le=60),
    db: Session = Depends(get_db),
):
    """Committed-spend timeline plus income/actual where recorded."""
    base = get_base_currency(db)
    ps = PriceService(base)
    expenses = db.query(Expense).all()
    records = {r.month: r for r in db.query(MonthlyRecord).all()}

    today = today_in(db)
    current = month_key(today)
    span = [
        shift_month(current, offset)
        for offset in range(-months_back, months_ahead + 1)
    ]
    wallet = _wallet_for_months(db, span, today)
    source_income = income_by_month(db, span, ps, base)

    timeline: list[TimelinePoint] = []
    category_series: list[dict] = []
    categories: set[str] = set()

    for m in span:
        committed, by_cat = committed_for_month(expenses, m, ps, base)
        categories.update(by_cat)
        row: dict = {"month": m}
        row.update({k: round(v, 2) for k, v in by_cat.items()})
        category_series.append(row)

        rec = records.get(m)
        src_total = source_income.get(m, {"total_in_base": 0.0})["total_in_base"]
        # A month counts as recorded either because it has a MonthlyRecord
        # (as before) or, new here, because an income source paid out in it -
        # but a future month never counts just for having an active source,
        # or a source that merely spans "today onward" would light up the
        # whole projection as if it were already known.
        recorded = rec is not None or (m <= current and src_total > 0)

        if not recorded:
            timeline.append(TimelinePoint(month=m, committed=round(committed, 2)))
            continue

        income_base_typed = (
            convert_currency(ps, float(rec.income), rec.currency, base)
            if rec is not None
            else 0.0
        )
        income_total = income_base_typed + src_total

        if rec is not None:
            actual_base = convert_currency(ps, float(rec.actual_spent), rec.currency, base)
            effective = effective_spend(income_total, *wallet[m])
            timeline.append(
                TimelinePoint(
                    month=m,
                    committed=round(committed, 2),
                    income=round(income_total, 2),
                    actual=round(actual_base, 2),
                    surplus=round(income_total - actual_base, 2),
                    effective=round(effective, 2) if effective is not None else None,
                )
            )
        else:
            # Source income only - no manually recorded actual spend to show.
            timeline.append(
                TimelinePoint(
                    month=m, committed=round(committed, 2), income=round(income_total, 2)
                )
            )

    recorded = [p for p in timeline if p.income is not None]
    with_income = [p for p in recorded if (p.income or 0) > 0 and p.surplus is not None]
    avg_income = (
        round(sum(p.income or 0 for p in recorded) / len(recorded), 2)
        if recorded
        else None
    )
    # Income can now come from sources in a month nobody typed spending into,
    # so each average runs over the months that actually carry its figure: a
    # missing spend is unknown, and counting it as 0 would flatter both the
    # spend and the savings rate that FIRE reads from here.
    with_spend = [p for p in recorded if p.actual is not None]
    avg_actual = (
        round(sum(p.actual for p in with_spend) / len(with_spend), 2)
        if with_spend
        else None
    )
    with_effective = [p for p in timeline if p.effective is not None]
    avg_effective = (
        round(sum(p.effective or 0 for p in with_effective) / len(with_effective), 2)
        if with_effective
        else None
    )
    avg_rate = (
        round(
            sum(100.0 * (p.surplus or 0) / (p.income or 1) for p in with_income)
            / len(with_income),
            1,
        )
        if with_income
        else None
    )

    return MonthlyAnalytics(
        base_currency=base,
        timeline=timeline,
        categories=sorted(categories),
        category_series=category_series,
        avg_income=avg_income,
        avg_actual=avg_actual,
        avg_effective=avg_effective,
        avg_savings_rate=avg_rate,
        months_recorded=len(recorded),
        months_with_spend=len(with_spend),
    )


@router.get("/{month}", response_model=MonthlyOut)
def get_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    base = get_base_currency(db)
    ps = PriceService(base)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    wallet = _wallet_for_months(db, [month], today_in(db))[month]
    source_income = income_by_month(db, [month], ps, base)
    return _build(
        month, record, db.query(Expense).all(), ps, base, wallet, source_income.get(month)
    )


@router.put("/{month}", response_model=MonthlyOut)
def upsert_month(month: str, payload: MonthlyIn, db: Session = Depends(get_db)):
    """Create or overwrite the figures for one month."""
    _validate_month(month)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        record = MonthlyRecord(month=month, **payload.model_dump())
        db.add(record)
    else:
        for field, value in payload.model_dump().items():
            setattr(record, field, value)
    db.commit()
    db.refresh(record)
    base = get_base_currency(db)
    ps = PriceService(base)
    wallet = _wallet_for_months(db, [month], today_in(db))[month]
    source_income = income_by_month(db, [month], ps, base)
    return _build(
        month, record, db.query(Expense).all(), ps, base, wallet, source_income.get(month)
    )


@router.patch("/{month}", response_model=MonthlyOut)
def patch_month(month: str, payload: MonthlyPatch, db: Session = Depends(get_db)):
    """Update only the fields sent, creating the record if missing.

    Spending (Expenses) and other income (Income) now edit this same row from
    two different pages; a PUT from either would carry its own zero/blank
    defaults for the fields it does not show and silently erase the other
    page's figure. PATCH only ever touches what the caller actually sent.
    """
    _validate_month(month)
    base = get_base_currency(db)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    if record is None:
        record = MonthlyRecord(
            month=month,
            income=fields.get("income", 0),
            actual_spent=fields.get("actual_spent", 0),
            currency=fields.get("currency", base),
            notes=fields.get("notes", ""),
        )
        db.add(record)
    else:
        for field, value in fields.items():
            setattr(record, field, value)
    db.commit()
    db.refresh(record)
    ps = PriceService(base)
    wallet = _wallet_for_months(db, [month], today_in(db))[month]
    source_income = income_by_month(db, [month], ps, base)
    return _build(
        month, record, db.query(Expense).all(), ps, base, wallet, source_income.get(month)
    )


@router.delete("/{month}", status_code=204)
def delete_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        raise HTTPException(404, "No record for that month")
    db.delete(record)
    db.commit()
