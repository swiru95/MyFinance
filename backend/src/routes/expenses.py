"""Recurring expense endpoints.

Expenses are standing commitments, deliberately kept separate from the asset
portfolio: they never affect the portfolio total, they only answer "what am I
committed to paying, and for how long".
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_db
from ..models.expense import Expense
from ..schemas.expense import ExpenseIn, ExpenseOut, ExpenseSummary
from ..services.price_service import PriceService
from .helpers import convert_currency, get_base_currency, today_in

router = APIRouter(prefix="/api/expenses", tags=["expenses"])

_ENDING_SOON_DAYS = 90


def _status(e: Expense, today: date) -> str:
    if e.starts_on > today:
        return "scheduled"
    if e.period == "once":
        return "ended" if e.starts_on < today else "active"
    # Recurring period (monthly, quarterly, yearly)
    if e.ends_on is not None and e.ends_on < today:
        return "ended"
    return "active"


def _decorate(e: Expense, ps: PriceService, base: str, today: date) -> ExpenseOut:
    from ..services.budget import monthly_equivalent, next_due

    out = ExpenseOut.model_validate(e)
    out.amount_in_base = round(
        convert_currency(ps, float(e.amount), e.currency, base), 2
    )
    out.base_currency = base
    out.status = _status(e, today)
    out.is_indefinite = e.period in ("monthly", "quarterly", "yearly") and e.ends_on is None

    # Compute next due date and monthly equivalent.
    out.next_due = next_due(e, today)
    equiv = monthly_equivalent(e)
    out.monthly_equivalent_in_base = round(
        convert_currency(ps, equiv, e.currency, base), 2
    )
    return out


def _all_decorated(db: Session) -> tuple[list[ExpenseOut], str]:
    base = get_base_currency(db)
    ps = PriceService(base)
    today = today_in(db)
    rows = db.query(Expense).order_by(Expense.starts_on.desc(), Expense.id.desc()).all()
    return [_decorate(e, ps, base, today) for e in rows], base


@router.get("", response_model=list[ExpenseOut])
def list_expenses(db: Session = Depends(get_db)):
    items, _ = _all_decorated(db)
    return items


@router.get("/summary", response_model=ExpenseSummary)
def expense_summary(db: Session = Depends(get_db)):
    """Monthly burn (as monthly equivalent) plus what is upcoming or about to end.

    For all recurring expenses (monthly, quarterly, yearly), uses the monthly
    equivalent amount to smooth budgeting — identical to today when everything
    is monthly. The dashboard runway uses this smoothed basis.

    A B2B source's income is already net of its ZUS/health contributions (see
    services/business_costs.py), so those never appear as a typed expense -
    they are added here, on top of monthly_total_personal, to get the full
    monthly_total a reserve actually has to cover. Callers that must stay
    personal-only (the monthly budget's committed figure, FIRE's post-FI
    spend fallback) read monthly_total_personal instead.
    """
    from ..services.business_costs import fixed_contributions
    from ..services.budget import month_key
    from ..services.price_service import PriceService

    items, base = _all_decorated(db)
    today = today_in(db)

    # Active recurring expenses (any period except once).
    active_recurring = [i for i in items if i.period != "once" and i.status == "active"]
    # Monthly total is the sum of monthly equivalents for active recurring.
    monthly_total_personal = sum(i.monthly_equivalent_in_base for i in active_recurring)

    business_contributions = fixed_contributions(
        db, month_key(today), PriceService(base), base
    )
    business_contributions_total = round(
        sum(c["total"] for c in business_contributions), 2
    )
    monthly_total = monthly_total_personal + business_contributions_total

    # Upcoming one-offs plus quarterly/yearly expenses due within 90 days.
    upcoming_oneoffs = sorted(
        (i for i in items if i.period == "once" and i.starts_on >= today),
        key=lambda i: i.starts_on,
    )
    upcoming_later = [
        i for i in items
        if i.period in ("quarterly", "yearly")
        and i.status == "active"
        and i.next_due is not None
        and (i.next_due - today).days <= 90
    ]
    upcoming = sorted(
        upcoming_oneoffs + upcoming_later,
        key=lambda i: i.next_due if i.period != "once" else i.starts_on,
    )

    # Ending soon: all active recurring with end date within 90 days.
    ending_soon = sorted(
        (
            i
            for i in active_recurring
            if i.ends_on is not None and (i.ends_on - today).days <= _ENDING_SOON_DAYS
        ),
        key=lambda i: i.ends_on,  # type: ignore[arg-type,return-value]
    )

    # By category: use monthly equivalents.
    by_cat: dict[str, float] = {}
    for i in active_recurring:
        by_cat[i.category or "Uncategorised"] = (
            by_cat.get(i.category or "Uncategorised", 0.0) + i.monthly_equivalent_in_base
        )
    by_category = [
        {"category": k, "total": round(v, 2)} for k, v in by_cat.items()
    ]
    if business_contributions_total > 0:
        # A stable id, not a typed category - "JDG: ZUS + health" is only
        # ever emitted here, so the frontend's data-string table (i18n.ts)
        # can translate it for PL the same way it does "Uncategorised".
        by_category.append(
            {"category": "JDG: ZUS + health", "total": business_contributions_total}
        )
    by_category.sort(key=lambda d: d["total"], reverse=True)

    return ExpenseSummary(
        base_currency=base,
        monthly_total=round(monthly_total, 2),
        monthly_total_personal=round(monthly_total_personal, 2),
        active_count=len(active_recurring),
        indefinite_count=sum(1 for i in active_recurring if i.is_indefinite),
        upcoming=upcoming,
        ending_soon=ending_soon,
        by_category=by_category,
        business_contributions=business_contributions,
        business_contributions_total=business_contributions_total,
    )


@router.post("", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseIn, db: Session = Depends(get_db)):
    e = Expense(**payload.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    base = get_base_currency(db)
    return _decorate(e, PriceService(base), base, today_in(db))


@router.get("/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: int, db: Session = Depends(get_db)):
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found")
    base = get_base_currency(db)
    return _decorate(e, PriceService(base), base, today_in(db))


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, payload: ExpenseIn, db: Session = Depends(get_db)):
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found")
    for field, value in payload.model_dump().items():
        setattr(e, field, value)
    db.commit()
    db.refresh(e)
    base = get_base_currency(db)
    return _decorate(e, PriceService(base), base, today_in(db))


@router.delete("/{expense_id}", status_code=204)
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    e = db.query(Expense).filter(Expense.id == expense_id).first()
    if not e:
        raise HTTPException(404, "Expense not found")
    db.delete(e)
    db.commit()
