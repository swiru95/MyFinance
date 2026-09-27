"""Polish statutory working-time calendar (wymiar czasu pracy).

A day/hour-billed B2B source's revenue really tracks the statutory full-time
working time for that month, not a fixed number of units - it moves with
weekends and public holidays exactly as an umowa o pracę employee's hours do.
This module is the single source of truth for that calendar so
services/income.py (per-month default) and routes/tax.py (the education view
and the comparator's default) never compute it twice.
"""
from __future__ import annotations

from datetime import date, timedelta


def easter(year: int) -> date:
    """Easter Sunday for `year` (anonymous Gregorian algorithm).

    Every other movable holiday below (Easter Monday, Pentecost, Corpus
    Christi) is defined relative to this one date, so getting it right once
    here is what makes the rest of the calendar trustworthy.
    """
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def public_holidays(year: int) -> dict[date, str]:
    """Statutory public holidays (dni ustawowo wolne od pracy) for `year`.

    24 Dec (Wigilia) only joined this list from 2025 onward - the statute
    that added it was signed in 2024, so a year before that has 13 holidays,
    not 14.
    """
    e = easter(year)
    holidays = {
        date(year, 1, 1): "Nowy Rok",
        date(year, 1, 6): "Trzech Króli",
        e: "Wielkanoc",
        e + timedelta(days=1): "Poniedziałek Wielkanocny",
        date(year, 5, 1): "Święto Pracy",
        date(year, 5, 3): "Święto Konstytucji 3 Maja",
        e + timedelta(days=49): "Zielone Świątki",
        e + timedelta(days=60): "Boże Ciało",
        date(year, 8, 15): "Wniebowzięcie Najświętszej Maryi Panny",
        date(year, 11, 1): "Wszystkich Świętych",
        date(year, 11, 11): "Narodowe Święto Niepodległości",
        date(year, 12, 25): "Boże Narodzenie (pierwszy dzień)",
        date(year, 12, 26): "Boże Narodzenie (drugi dzień)",
    }
    if year >= 2025:
        holidays[date(year, 12, 24)] = "Wigilia"
    return holidays


def working_days(year: int, month: int) -> int:
    """Statutory full-time working days (wymiar czasu pracy) for one month.

    Mon-Fri days in the month, minus one day for every holiday landing
    Monday through Saturday - art. 130 §2 Kodeksu pracy: a public holiday on
    any day other than Sunday reduces the working-time norm by 8h, so a
    holiday that falls on a Saturday (never a working day itself) still
    costs a weekday's worth of hours.
    """
    first = date(year, month, 1)
    next_month = date(year + (month == 12), (month % 12) + 1, 1)
    days_in_month = (next_month - first).days
    weekdays = sum(
        1 for d in range(days_in_month) if (first + timedelta(days=d)).weekday() < 5
    )
    reductions = sum(
        1
        for d in public_holidays(year)
        if d.year == year and d.month == month and d.weekday() != 6
    )
    return weekdays - reductions


def working_hours(year: int, month: int) -> int:
    """8h × `working_days` - the statutory monthly hour norm."""
    return 8 * working_days(year, month)


def year_calendar(year: int) -> list[dict]:
    """Every month of `year`: working days, working hours, and the holidays
    that fell in it. Totals are a plain sum of this list, deliberately not
    duplicated onto each row."""
    holidays = public_holidays(year)
    months: list[dict] = []
    for month in range(1, 13):
        month_holidays = sorted(
            (
                {"date": d.isoformat(), "name": name}
                for d, name in holidays.items()
                if d.year == year and d.month == month
            ),
            key=lambda h: h["date"],
        )
        months.append(
            {
                "month": month,
                "working_days": working_days(year, month),
                "working_hours": working_hours(year, month),
                "holidays": month_holidays,
            }
        )
    return months
