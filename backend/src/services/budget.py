"""Month-level budget maths shared by the monthly endpoints.

The committed spend for a month is always derived from the recurring expense
definitions rather than stored, so correcting an expense fixes history too.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..models.expense import Expense
from ..routes.helpers import convert_currency
from ..services.price_service import PriceService

MONTH_RE = r"^\d{4}-(0[1-9]|1[0-2])$"


def month_bounds(month: str) -> tuple[date, date]:
    """First and last day of a "YYYY-MM" month."""
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    nxt = date(year + (mon == 12), (mon % 12) + 1, 1)
    return first, nxt - timedelta(days=1)


def wallet_window(month: str, today: date) -> tuple[date, date] | None:
    """The two days a month's portfolio change is measured between.

    The opening balance is the *previous* month's closing value, not the 1st:
    a snapshot taken on the 1st already includes whatever happened that day.
    A month still running is measured up to today rather than to a last day
    that has not arrived yet; a month entirely in the future has no window.
    """
    first, last = month_bounds(month)
    if today < first:
        return None
    return first - timedelta(days=1), min(last, today)


def effective_spend(
    income_in_base: float, wallet_start: float | None, wallet_end: float | None
) -> float | None:
    """What was really spent, read off the portfolio rather than typed in.

    Everything earned either sits in the portfolio at the end of the month or
    has been spent, so income minus the change in portfolio value is the spend
    - including the spending that never gets entered as an expense.

    None unless there is income to subtract from and a snapshot on both ends:
    without an opening value the change is unknown, and an unknown change would
    silently turn into "you spent your entire income".
    """
    if income_in_base <= 0 or wallet_start is None or wallet_end is None:
        return None
    return income_in_base - (wallet_end - wallet_start)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def shift_month(month: str, delta: int) -> str:
    """Move a "YYYY-MM" key by `delta` months."""
    year, mon = int(month[:4]), int(month[5:7])
    total = year * 12 + (mon - 1) + delta
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def applies_in_month(e: Expense, first: date, last: date) -> bool:
    """Is this expense charged at all during [first, last]?"""
    if e.period == "once":
        return first <= e.starts_on <= last
    if e.starts_on > last:
        return False
    return e.ends_on is None or e.ends_on >= first


def committed_for_month(
    expenses: list[Expense], month: str, ps: PriceService, base: str
) -> tuple[float, dict[str, float]]:
    """Total committed spend for `month` plus a per-category breakdown."""
    first, last = month_bounds(month)
    total = 0.0
    by_category: dict[str, float] = {}
    for e in expenses:
        if not applies_in_month(e, first, last):
            continue
        value = convert_currency(ps, float(e.amount), e.currency, base)
        total += value
        key = e.category or "Uncategorised"
        by_category[key] = by_category.get(key, 0.0) + value
    return total, by_category
