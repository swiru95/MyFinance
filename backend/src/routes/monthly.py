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
    month_key,
    shift_month,
)
from ..services.price_service import PriceService
from .helpers import convert_currency, get_base_currency, today_in

router = APIRouter(prefix="/api/monthly", tags=["monthly"])

import re

_MONTH_PATTERN = re.compile(MONTH_RE)


def _validate_month(month: str) -> str:
    if not _MONTH_PATTERN.match(month):
        raise HTTPException(422, "month must be in YYYY-MM form")
    return month


def _build(
    month: str,
    record: MonthlyRecord | None,
    expenses: list[Expense],
    ps: PriceService,
    base: str,
) -> MonthlyOut:
    committed, by_cat = committed_for_month(expenses, month, ps, base)
    currency = record.currency if record else base
    income = float(record.income) if record else 0.0
    actual = float(record.actual_spent) if record else 0.0
    income_base = convert_currency(ps, income, currency, base)
    actual_base = convert_currency(ps, actual, currency, base)
    surplus = income_base - actual_base
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
    current = month_key(today_in(db))
    months = set(records) | {current}
    return [
        _build(m, records.get(m), expenses, ps, base)
        for m in sorted(months, reverse=True)
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

    current = month_key(today_in(db))
    span = [
        shift_month(current, offset)
        for offset in range(-months_back, months_ahead + 1)
    ]

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
            timeline.append(
                TimelinePoint(
                    month=m,
                    committed=round(committed, 2),
                    income=round(income_base, 2),
                    actual=round(actual_base, 2),
                    surplus=round(income_base - actual_base, 2),
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
        avg_savings_rate=avg_rate,
        months_recorded=len(recorded),
    )


@router.get("/{month}", response_model=MonthlyOut)
def get_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    base = get_base_currency(db)
    ps = PriceService(base)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    return _build(month, record, db.query(Expense).all(), ps, base)


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
    return _build(month, record, db.query(Expense).all(), PriceService(base), base)


@router.delete("/{month}", status_code=204)
def delete_month(month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        raise HTTPException(404, "No record for that month")
    db.delete(record)
    db.commit()
