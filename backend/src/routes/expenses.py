"""Recurring expense endpoints.

Expenses are standing commitments, deliberately kept separate from the asset
portfolio: they never affect the portfolio total, they only answer "what am I
committed to paying, and for how long".
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
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
    if e.ends_on is not None and e.ends_on < today:
        return "ended"
    return "active"


def _decorate(e: Expense, ps: PriceService, base: str, today: date) -> ExpenseOut:
    out = ExpenseOut.model_validate(e)
    out.amount_in_base = round(
        convert_currency(ps, float(e.amount), e.currency, base), 2
    )
    out.base_currency = base
    out.status = _status(e, today)
    out.is_indefinite = e.period == "monthly" and e.ends_on is None
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
    """Monthly burn plus what is upcoming or about to end."""
    items, base = _all_decorated(db)
    today = today_in(db)

    active_monthly = [i for i in items if i.period == "monthly" and i.status == "active"]
    monthly_total = sum(i.amount_in_base for i in active_monthly)

    upcoming = sorted(
        (i for i in items if i.period == "once" and i.starts_on >= today),
        key=lambda i: i.starts_on,
    )
    ending_soon = sorted(
        (
            i
            for i in active_monthly
            if i.ends_on is not None and (i.ends_on - today).days <= _ENDING_SOON_DAYS
        ),
        key=lambda i: i.ends_on,  # type: ignore[arg-type,return-value]
    )

    by_cat: dict[str, float] = {}
    for i in active_monthly:
        by_cat[i.category or "Uncategorised"] = (
            by_cat.get(i.category or "Uncategorised", 0.0) + i.amount_in_base
        )
    by_category = sorted(
        ({"category": k, "total": round(v, 2)} for k, v in by_cat.items()),
        key=lambda d: d["total"],
        reverse=True,
    )

    return ExpenseSummary(
        base_currency=base,
        monthly_total=round(monthly_total, 2),
        active_count=len(active_monthly),
        indefinite_count=sum(1 for i in active_monthly if i.is_indefinite),
        upcoming=upcoming,
        ending_soon=ending_soon,
        by_category=by_category,
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
