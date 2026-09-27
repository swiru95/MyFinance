"""Golden working-time calendar values, hand-checked by the architect against
published 2025/2026 wymiar czasu pracy tables."""
from src.tax.pl.calendar import easter, public_holidays, working_days, working_hours, year_calendar


def test_easter_2026():
    assert easter(2026).isoformat() == "2026-04-05"


def test_easter_2025():
    assert easter(2025).isoformat() == "2025-04-20"


def test_working_days_2026_per_month():
    days = [working_days(2026, m) for m in range(1, 13)]
    assert days == [20, 20, 22, 21, 20, 21, 23, 20, 22, 22, 20, 20]
    assert sum(days) == 251
    assert sum(working_hours(2026, m) for m in range(1, 13)) == 2008


def test_working_days_2025_per_month():
    days = [working_days(2025, m) for m in range(1, 13)]
    assert days == [21, 20, 21, 21, 20, 20, 23, 20, 22, 23, 18, 20]
    assert sum(days) == 249
    assert sum(working_hours(2025, m) for m in range(1, 13)) == 1992


def test_november_2025_saturday_holiday_costs_a_weekday():
    # Nov 1 2025 (Wszystkich Świętych) is a Saturday, so it still reduces
    # the month's working-time norm by one day - 18, not 19.
    assert working_days(2025, 11) == 18


def test_wigilia_only_from_2025():
    from datetime import date

    assert date(2025, 12, 24) in public_holidays(2025)
    assert date(2024, 12, 24) not in public_holidays(2024)


def test_year_calendar_shape_and_totals():
    cal = year_calendar(2026)
    assert len(cal) == 12
    assert [m["month"] for m in cal] == list(range(1, 13))
    assert sum(m["working_days"] for m in cal) == 251
    assert sum(m["working_hours"] for m in cal) == 2008
    jan = cal[0]
    assert {"date": "2026-01-01", "name": "Nowy Rok"} in jan["holidays"]
