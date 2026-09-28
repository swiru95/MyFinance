"""Monthly budget + analytics endpoints."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.expense import Expense
from ..models.income import IncomeSource
from ..models.monthly import MonthlyRecord
from ..schemas.monthly import (
    CommitmentInput,
    CommitmentOut,
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
    expenses_applying_in_month,
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


def _compute_actual_from_breakdown(
    commitments_paid_json: str,
    other_spent: float,
    target_currency: str,
    ps: PriceService,
) -> float:
    """Compute actual_spent from the breakdown (commitments + other) in a
    given target currency. Uses the same currency conversion logic as the
    breakdown path itself - see routes/monthly.py for usage."""
    saved_entries = json.loads(commitments_paid_json)
    paid_total = sum(
        convert_currency(ps, e["amount"], e["currency"], target_currency)
        for e in saved_entries
        if e.get("paid")
    )
    return round(paid_total + float(other_spent), 2)


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

    # The checklist breakdown behind actual_spent, in the record's own
    # currency - see models/monthly.MonthlyRecord. Both columns are always
    # written together (routes.monthly._apply_month_write), so either being
    # set means this is a breakdown record, not a legacy one-total record.
    commitments_paid_total = None
    other_spent_out = None
    breakdown = False
    if record is not None and record.commitments_paid is not None and record.other_spent is not None:
        breakdown = True
        entries = json.loads(record.commitments_paid)
        commitments_paid_total = round(
            sum(
                convert_currency(ps, e["amount"], e["currency"], currency)
                for e in entries
                if e.get("paid")
            ),
            2,
        )
        other_spent_out = round(float(record.other_spent), 2)
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
        commitments_paid_total=commitments_paid_total,
        other_spent=other_spent_out,
        breakdown=breakdown,
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


def _apply_month_write(
    record: MonthlyRecord,
    *,
    income: float | None,
    actual_spent: float | None,
    currency: str | None,
    notes: str | None,
    commitments: list[CommitmentInput] | None,
    other_spent: float | None,
    db: Session,
    ps: PriceService,
) -> None:
    """Write the given fields onto `record`.

    Shared by PUT (always sends every MonthlyIn field) and PATCH (sends only
    what changed) - the caller passes None for anything it does not want
    touched. When `commitments` or `other_spent` is given, actual_spent is
    derived from the checklist and any `actual_spent` passed in is ignored;
    otherwise actual_spent is written as given, exactly like before this
    checklist existed (the legacy "one total" path).
    """
    if currency is not None:
        record.currency = currency
    if income is not None:
        record.income = income
    if notes is not None:
        record.notes = notes

    breakdown_write = commitments is not None or other_spent is not None
    if not breakdown_write:
        if actual_spent is not None:
            record.actual_spent = actual_spent
            # Legacy write onto a breakdown record: clear the breakdown columns
            # so the plain total becomes the single source of truth, otherwise
            # stale breakdown data would stay in the DB (see models/monthly.py).
            record.commitments_paid = None
            record.other_spent = None
        elif (
            currency is not None
            and record.commitments_paid is not None
            and record.other_spent is not None
        ):
            # Currency-only change on a breakdown record: recompute actual_spent
            # in the new currency using the saved breakdown, keeping the
            # breakdown data intact (see models/monthly.py).
            record.actual_spent = _compute_actual_from_breakdown(
                record.commitments_paid,
                float(record.other_spent),
                record.currency,
                ps,
            )
        return

    if commitments is not None:
        entries = []
        for c in commitments:
            expense = db.query(Expense).filter(Expense.id == c.expense_id).first()
            if expense is None:
                raise HTTPException(422, f"Unknown expense_id: {c.expense_id}")
            entries.append({
                "expense_id": c.expense_id,
                "name": expense.name,
                "amount": c.amount,
                "currency": expense.currency,
                "paid": c.paid,
            })
        record.commitments_paid = json.dumps(entries)
    elif record.commitments_paid is None:
        # Entering breakdown mode via other_spent alone (no commitments sent
        # this call) - keep the columns paired so "breakdown" (both non-null)
        # stays a reliable signal, per models/monthly.py.
        record.commitments_paid = "[]"

    if other_spent is not None:
        record.other_spent = other_spent
    elif record.other_spent is None:
        record.other_spent = 0.0

    record.actual_spent = _compute_actual_from_breakdown(
        record.commitments_paid,
        float(record.other_spent),
        record.currency,
        ps,
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


@router.get("/{month}/commitments", response_model=list[CommitmentOut])
def month_commitments(month: str, db: Session = Depends(get_db)):
    """The commitments charged in `month` - the month checklist's rows.

    Every Expense for which applies_in_month is true (cash view - a yearly
    bill appears in full in its charge month), defaulted to "paid as usual"
    at its own amount. Once the month has a saved breakdown, paid/amount
    come from it instead, and an expense that was saved but no longer
    applies (period/dates edited since, or the expense deleted) is still
    listed, from the saved data, so a previous save is never silently lost
    from the checklist. JDG ZUS/health are never Expense rows (they live in
    services/business_costs.py) and so never appear here.
    """
    _validate_month(month)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    expenses = db.query(Expense).all()
    expense_by_id = {e.id: e for e in expenses}
    applying = expenses_applying_in_month(expenses, month)
    applying_ids = {e.id for e in applying}

    saved_entries = (
        json.loads(record.commitments_paid)
        if record is not None and record.commitments_paid is not None
        else None
    )
    saved_by_id = {e["expense_id"]: e for e in saved_entries} if saved_entries else {}

    rows: list[CommitmentOut] = []
    for e in applying:
        s = saved_by_id.get(e.id)
        if saved_entries is not None and s is not None:
            rows.append(CommitmentOut(
                expense_id=e.id,
                name=s.get("name") or e.name,
                category=e.category,
                amount=s["amount"],
                currency=s.get("currency", e.currency),
                paid=s["paid"],
            ))
        else:
            rows.append(CommitmentOut(
                expense_id=e.id,
                name=e.name,
                category=e.category,
                amount=float(e.amount),
                currency=e.currency,
                paid=True,
            ))

    if saved_entries is not None:
        for eid, s in saved_by_id.items():
            if eid in applying_ids:
                continue
            e = expense_by_id.get(eid)
            rows.append(CommitmentOut(
                expense_id=eid,
                name=s.get("name") or "",
                category=e.category if e else "",
                amount=s["amount"],
                currency=s.get("currency", "PLN"),
                paid=s["paid"],
            ))

    rows.sort(key=lambda r: (r.category, r.name))
    return rows


@router.put("/{month}", response_model=MonthlyOut)
def upsert_month(month: str, payload: MonthlyIn, db: Session = Depends(get_db)):
    """Create or overwrite the figures for one month."""
    _validate_month(month)
    base = get_base_currency(db)
    ps = PriceService(base)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        record = MonthlyRecord(
            month=month, income=0, actual_spent=0, currency=payload.currency, notes=""
        )
        db.add(record)
    _apply_month_write(
        record,
        income=payload.income,
        actual_spent=payload.actual_spent,
        currency=payload.currency,
        notes=payload.notes,
        commitments=payload.commitments,
        other_spent=payload.other_spent,
        db=db,
        ps=ps,
    )
    db.commit()
    db.refresh(record)
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
    ps = PriceService(base)
    record = db.query(MonthlyRecord).filter(MonthlyRecord.month == month).first()
    if record is None:
        record = MonthlyRecord(
            month=month,
            income=payload.income or 0,
            actual_spent=0,
            currency=payload.currency or base,
            notes=payload.notes or "",
        )
        db.add(record)
    _apply_month_write(
        record,
        income=payload.income,
        actual_spent=payload.actual_spent,
        currency=payload.currency,
        notes=payload.notes,
        commitments=payload.commitments,
        other_spent=payload.other_spent,
        db=db,
        ps=ps,
    )
    db.commit()
    db.refresh(record)
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
