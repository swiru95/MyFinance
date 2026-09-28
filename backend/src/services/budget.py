"""Month-level budget maths shared by the monthly endpoints.

The committed spend for a month is always derived from the recurring expense
definitions rather than stored, so correcting an expense fixes history too.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from ..models.expense import Expense
from ..services.price_service import PriceService

MONTH_RE = r"^\d{4}-(0[1-9]|1[0-2])$"
PERIOD_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}


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
    """Is this expense charged at all during [first, last]?

    For recurring expenses (monthly, quarterly, yearly), the charge date is
    the same day of the month as starts_on, in each period where it recurs.
    """
    if e.period == "once":
        return first <= e.starts_on <= last
    if e.starts_on > last:
        return False
    if e.ends_on is not None and e.ends_on < first:
        return False

    if e.period == "monthly":
        return True

    # For quarterly/yearly: check if any month in [first, last] is a recurring month.
    period_months = PERIOD_MONTHS[e.period]
    year, month = first.year, first.month
    while date(year, month, 1) <= last:
        # Count months between starts_on month and this month.
        # If divisible by period_months and >= 0, it's a recurring month.
        m_diff = (year - e.starts_on.year) * 12 + (month - e.starts_on.month)
        if m_diff >= 0 and m_diff % period_months == 0:
            return True
        # Advance to next month.
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return False


def expenses_applying_in_month(expenses: list[Expense], month: str) -> list[Expense]:
    """Every expense charged at all during `month` (cash view).

    Shared by the month-checklist endpoint (GET .../commitments) and
    demo_seed, so both agree with committed_for_month on which expenses a
    given month covers.
    """
    first, last = month_bounds(month)
    return [e for e in expenses if applies_in_month(e, first, last)]


def monthly_equivalent(e: Expense) -> float:
    """Monthly equivalent of a recurring expense.

    For monthly expenses, this is the amount itself. For quarterly/yearly,
    it is the amount divided by the period in months. For one-offs, it is 0.
    """
    if e.period == "once":
        return 0.0
    period_months = PERIOD_MONTHS.get(e.period, 1)
    return float(e.amount) / period_months


def next_due(e: Expense, today: date) -> date | None:
    """Next charge date for this expense on or after today.

    For once-only expenses, returns starts_on if it's today or future, else None.
    For recurring expenses, calculates the next occurrence based on the period.
    Returns None if the expense has ended.
    """
    if e.period == "once":
        return e.starts_on if e.starts_on >= today else None

    if e.ends_on is not None and e.ends_on < today:
        return None

    if today <= e.starts_on:
        return e.starts_on

    step = PERIOD_MONTHS.get(e.period, 1)
    months_diff = (today.year - e.starts_on.year) * 12 + (today.month - e.starts_on.month)
    # The first charge in or after today's month; if that one has already
    # passed this month (its day is behind today), the one after it.
    offset = -(-months_diff // step) * step
    due = _charge_date(e.starts_on, offset)
    if due < today:
        due = _charge_date(e.starts_on, offset + step)
    if e.ends_on is not None and due > e.ends_on:
        return None
    return due


def _charge_date(start: date, months: int) -> date:
    """`start` moved by whole months, the day clamped to the month's length.

    A charge set up on the 31st falls on the 28th/29th in February rather than
    spilling into March.
    """
    total = start.year * 12 + (start.month - 1) + months
    year, month = total // 12, total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def committed_for_month(
    expenses: list[Expense], month: str, ps: PriceService, base: str
) -> tuple[float, dict[str, float]]:
    """Total committed spend for `month` plus a per-category breakdown.

    The cash view: a yearly or quarterly expense counts in full in the months
    it is charged and not at all in between, because this is what the month's
    budget actually has to cover. The smoothed view (`monthly_equivalent`) is
    for planning figures such as the runway reserve.
    """
    # Imported here: routes/__init__ pulls in routes.monthly, whose schemas
    # import this module, so a top-level import is circular whenever this
    # module is imported first.
    from ..routes.helpers import convert_currency

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
