"""Monthly budget + analytics endpoints."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.expense import Expense
from ..models.monthly import MonthlyRecord
from ..schemas.monthly import (
    MonthlyAnalytics,
    MonthlyIn,
    MonthlyOut,
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
) -> MonthlyOut:
    committed, by_cat = committed_for_month(expenses, month, ps, base)
    currency = record.currency if record else base
    income = float(record.income) if record else 0.0
    actual = float(record.actual_spent) if record else 0.0
    income_base = convert_currency(ps, income, currency, base)
    actual_base = convert_currency(ps, actual, currency, base)
    surplus = income_base - actual_base
    wallet_start, wallet_end = wallet
    change = (
        round(wallet_end - wallet_start, 2)
        if wallet_start is not None and wallet_end is not None
        else None
    )
    effective = effective_spend(income_base, wallet_start, wallet_end)
    return MonthlyOut(
        month=month,
        income=income,
        actual_spent=actual,
        currency=currency,
        notes=record.notes if record else "",
        base_currency=base,
        income_in_base=round(income_base, 2),
        actual_in_base=round(actual_base, 2),
        committed=round(committed, 2),
        surplus=round(surplus, 2),
        savings_rate=round(100.0 * surplus / income_base, 1) if income_base else None,
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

    The current month is synthesised when it has not been filled in yet, so the
    page always has a row to type into without leaving empty rows in the table.
    """
    base = get_base_currency(db)
    ps = PriceService(base)
    expenses = db.query(Expense).all()
    records = {r.month: r for r in db.query(MonthlyRecord).all()}
    today = today_in(db)
    current = month_key(today)
    months = sorted(set(records) | {current}, reverse=True)
    wallet = _wallet_for_months(db, months, today)
    return [
        _build(m, records.get(m), expenses, ps, base, wallet[m]) for m in months
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
        if rec is not None:
            income_base = convert_currency(ps, float(rec.income), rec.currency, base)
            actual_base = convert_currency(
                ps, float(rec.actual_spent), rec.currency, base
            )
            effective = effective_spend(income_base, *wallet[m])
            timeline.append(
                TimelinePoint(
                    month=m,
                    committed=round(committed, 2),
                    income=round(income_base, 2),
                    actual=round(actual_base, 2),
                    surplus=round(income_base - actual_base, 2),
                    effective=round(effective, 2) if effective is not None else None,
                )
            )
        else:
            timeline.append(TimelinePoint(month=m, committed=round(committed, 2)))

    recorded = [p for p in timeline if p.income is not None]
    with_income = [p for p in recorded if (p.income or 0) > 0]
    avg_income = (
        round(sum(p.income or 0 for p in recorded) / len(recorded), 2)
        if recorded
        else None
    )
    avg_actual = (
        round(sum(p.actual or 0 for p in recorded) / len(recorded), 2)
        if recorded
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
    )


@router.get("/{month}", response_model=MonthlyOut)
def get_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    base = get_base_currency(db)
    ps = PriceService(base)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    wallet = _wallet_for_months(db, [month], today_in(db))[month]
    return _build(month, record, db.query(Expense).all(), ps, base, wallet)


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
    wallet = _wallet_for_months(db, [month], today_in(db))[month]
    return _build(
        month, record, db.query(Expense).all(), PriceService(base), base, wallet
    )


@router.delete("/{month}", status_code=204)
def delete_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        raise HTTPException(404, "No record for that month")
    db.delete(record)
    db.commit()
