"""Income source endpoints: recurring income definitions, month overrides,
the per-source tax-engine breakdown, and a wallet-wide monthly summary with
the b2b "set-aside" envelope.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.income import IncomeEntry, IncomeSource
from ..schemas.income import (
    PARAM_MODELS,
    IncomeEntryIn,
    IncomeEntryOut,
    IncomeSourceIn,
    IncomeSourceOut,
)
from ..services.budget import MONTH_RE
from ..services.income import source_year
from ..services.price_service import PriceService
from ..tax.pl.b2b import DUE_DAYS
from ..tax.pl.params import EARLIEST_YEAR, money
from .helpers import convert_currency, get_base_currency, today_in

import re

router = APIRouter(prefix="/api/income", tags=["income"])

_MONTH_PATTERN = re.compile(MONTH_RE)


def _validate_month(month: str) -> str:
    if not _MONTH_PATTERN.match(month):
        raise HTTPException(422, "month must be in YYYY-MM form")
    return month


def _entries_by_source(db: Session) -> dict[int, list[IncomeEntry]]:
    out: dict[int, list[IncomeEntry]] = {}
    for e in db.query(IncomeEntry).all():
        out.setdefault(e.source_id, []).append(e)
    return out


def _decorate(
    src: IncomeSource,
    entries: list[IncomeEntry],
    ps: PriceService,
    base: str,
    today: date,
) -> IncomeSourceOut:
    sy = source_year(src, entries, today.year, ps, base)
    current_key = f"{today.year:04d}-{today.month:02d}"
    current_month = next((m for m in sy["months"] if m["month"] == current_key), {})
    year_summary = {k: v for k, v in sy.items() if k != "months"}

    out = IncomeSourceOut.model_validate(src)
    out.year_summary = year_summary
    out.current_month = current_month
    return out


@router.get("/sources", response_model=list[IncomeSourceOut])
def list_sources(db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    today = today_in(db)
    sources = (
        db.query(IncomeSource)
        .order_by(IncomeSource.starts_on.desc(), IncomeSource.id.desc())
        .all()
    )
    entries_by_source = _entries_by_source(db)
    return [
        _decorate(s, entries_by_source.get(s.id, []), ps, base, today) for s in sources
    ]


@router.post("/sources", response_model=IncomeSourceOut, status_code=201)
def create_source(payload: IncomeSourceIn, db: Session = Depends(get_db)):
    src = IncomeSource(**payload.model_dump())
    db.add(src)
    db.commit()
    db.refresh(src)
    base = get_base_currency(db)
    return _decorate(src, [], PriceService(base), base, today_in(db))


@router.put("/sources/{source_id}", response_model=IncomeSourceOut)
def update_source(source_id: int, payload: IncomeSourceIn, db: Session = Depends(get_db)):
    src = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not src:
        raise HTTPException(404, "Income source not found")
    for field, value in payload.model_dump().items():
        setattr(src, field, value)
    db.commit()
    db.refresh(src)
    base = get_base_currency(db)
    entries = db.query(IncomeEntry).filter(IncomeEntry.source_id == source_id).all()
    return _decorate(src, entries, PriceService(base), base, today_in(db))


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: int, db: Session = Depends(get_db)):
    src = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not src:
        raise HTTPException(404, "Income source not found")
    # SQLite does not enforce FK cascades by default, so entries are removed
    # explicitly rather than relying on the schema to clean them up.
    db.query(IncomeEntry).filter(IncomeEntry.source_id == source_id).delete()
    db.delete(src)
    db.commit()


@router.get("/sources/{source_id}/year/{year}")
def get_source_year(source_id: int, year: int, db: Session = Depends(get_db)):
    _require_rules(year)
    src = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not src:
        raise HTTPException(404, "Income source not found")
    entries = db.query(IncomeEntry).filter(IncomeEntry.source_id == source_id).all()
    base = get_base_currency(db)
    return source_year(src, entries, year, PriceService(base), base)


def _require_rules(year: int) -> None:
    if year < EARLIEST_YEAR:
        raise HTTPException(
            422, f"Tax rules for {year} are not loaded; the earliest is {EARLIEST_YEAR}"
        )


def _resolve_entry_amount(src: IncomeSource, payload: IncomeEntryIn) -> float:
    """The revenue/gross/net to freeze onto the entry.

    An explicit amount always wins. Otherwise, only a daily/hourly b2b
    source can fall back to `rate x units` - every other kind/billing has no
    calendar behind it, so `amount` stays required for it (422).
    """
    if payload.amount is not None:
        return payload.amount
    if src.kind == "b2b":
        params_model = PARAM_MODELS["b2b"].model_validate(src.params)
        if params_model.billing in ("daily", "hourly") and payload.units is not None:
            return money(float(params_model.rate or 0.0) * payload.units)
    raise HTTPException(
        422, "amount is required unless units is given for a daily/hourly b2b source"
    )


@router.put("/sources/{source_id}/entries/{month}", response_model=IncomeEntryOut)
def upsert_entry(
    source_id: int, month: str, payload: IncomeEntryIn, db: Session = Depends(get_db)
):
    _validate_month(month)
    src = db.query(IncomeSource).filter(IncomeSource.id == source_id).first()
    if not src:
        raise HTTPException(404, "Income source not found")
    data = payload.model_dump()
    data["amount"] = _resolve_entry_amount(src, payload)
    entry = (
        db.query(IncomeEntry)
        .filter(IncomeEntry.source_id == source_id, IncomeEntry.month == month)
        .first()
    )
    if entry is None:
        entry = IncomeEntry(source_id=source_id, month=month, **data)
        db.add(entry)
    else:
        for field, value in data.items():
            setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/sources/{source_id}/entries/{month}", status_code=204)
def delete_entry(source_id: int, month: str, db: Session = Depends(get_db)):
    _validate_month(month)
    entry = (
        db.query(IncomeEntry)
        .filter(IncomeEntry.source_id == source_id, IncomeEntry.month == month)
        .first()
    )
    if entry is None:
        raise HTTPException(404, "No entry for that month")
    db.delete(entry)
    db.commit()


@router.get("/summary")
def income_summary(year: int | None = Query(None), db: Session = Depends(get_db)):
    """12 months of totals in base currency, plus the b2b "set-aside"
    envelope: for the previous and current month, what to keep untouched for
    ZUS/health, PIT and VAT, with its due date and whether that window has
    already passed.
    """
    base = get_base_currency(db)
    ps = PriceService(base)
    today = today_in(db)
    year = year or today.year
    _require_rules(year)

    sources = db.query(IncomeSource).all()
    entries_by_source = _entries_by_source(db)
    source_years = {
        src.id: source_year(src, entries_by_source.get(src.id, []), year, ps, base)
        for src in sources
    }

    keys = ("net", "gross", "social", "health", "pit", "ppk", "vat_due")
    annual = {k: 0.0 for k in keys}
    months_out = []

    for i in range(12):
        month_str = f"{year:04d}-{i + 1:02d}"
        totals = {k: 0.0 for k in keys}
        for src in sources:
            row = next(
                (m for m in source_years[src.id]["months"] if m["month"] == month_str), None
            )
            if row is None or not (row["active"] or row["has_entry"]):
                continue
            breakdown = row["breakdown"] or {}
            totals["net"] += row["net_in_base"]
            if src.kind == "uop":
                totals["gross"] += convert_currency(ps, breakdown.get("gross", 0.0), "PLN", base)
                totals["social"] += convert_currency(
                    ps, breakdown.get("employee_social", 0.0), "PLN", base
                )
                totals["health"] += convert_currency(ps, breakdown.get("health", 0.0), "PLN", base)
                totals["pit"] += convert_currency(
                    ps, breakdown.get("pit_advance", 0.0), "PLN", base
                )
                totals["ppk"] += convert_currency(
                    ps, breakdown.get("ppk_employee", 0.0), "PLN", base
                )
            elif src.kind == "b2b":
                totals["gross"] += convert_currency(ps, breakdown.get("revenue", 0.0), "PLN", base)
                totals["social"] += convert_currency(
                    ps, breakdown.get("social_total", 0.0), "PLN", base
                )
                totals["health"] += convert_currency(ps, breakdown.get("health", 0.0), "PLN", base)
                totals["pit"] += convert_currency(
                    ps, breakdown.get("pit_advance", 0.0), "PLN", base
                )
                totals["vat_due"] += convert_currency(
                    ps, breakdown.get("vat_due", 0.0), "PLN", base
                )
        for k in keys:
            annual[k] += totals[k]
        months_out.append({"month": month_str, **{k: money(v) for k, v in totals.items()}})

    # Envelope: previous + current month, b2b sources only.
    current_key = f"{today.year:04d}-{today.month:02d}"
    if today.month > 1:
        prev_key = f"{today.year:04d}-{today.month - 1:02d}"
    else:
        prev_key = f"{today.year - 1:04d}-12"

    envelope = []
    outstanding_total = 0.0
    for src in sources:
        if src.kind != "b2b":
            continue
        for key in (prev_key, current_key):
            key_year, key_month = int(key[:4]), int(key[5:7])
            sy = (
                source_years[src.id]
                if key_year == year
                else source_year(src, entries_by_source.get(src.id, []), key_year, ps, base)
            )
            row = next((m for m in sy["months"] if m["month"] == key), None)
            if row is None or not (row["active"] or row["has_entry"]):
                continue
            breakdown = row["breakdown"] or {}
            due_year, due_month = (
                (key_year, key_month + 1) if key_month < 12 else (key_year + 1, 1)
            )
            components = {
                "zus": breakdown.get("social_total", 0.0) + breakdown.get("health", 0.0),
                "pit": breakdown.get("pit_advance", 0.0),
                "vat": max(breakdown.get("vat_due", 0.0), 0.0),
            }
            item = {"source_id": src.id, "name": src.name, "month": key}
            for comp, amount_pln in components.items():
                due_date = date(due_year, due_month, DUE_DAYS[comp])
                amount_in_base = money(convert_currency(ps, amount_pln, "PLN", base))
                status = "paid_window_passed" if due_date < today else "outstanding"
                item[comp] = {
                    "amount_in_base": amount_in_base,
                    "due_date": due_date.isoformat(),
                    "status": status,
                }
                if status == "outstanding":
                    outstanding_total += amount_in_base
            envelope.append(item)

    return {
        "year": year,
        "base_currency": base,
        "months": months_out,
        "annual": {k: money(v) for k, v in annual.items()},
        "envelope": envelope,
        "envelope_outstanding_in_base": money(outstanding_total),
    }
