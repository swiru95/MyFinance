"""services/grounding.check_grounding: every number in the model's text has
to trace back to the snapshot, tolerating locale formatting and rounding.
"""
from src.services.grounding import check_grounding


def test_english_thousands_and_decimal_format_matches():
    snap = {"total_value": 12400}
    assert check_grounding("Your total is PLN 12,400.00 today.", snap) == []


def test_polish_space_thousands_and_comma_decimal_matches():
    snap = {"total_value": 12400}
    assert check_grounding("Twoja suma to 12 400,00 zł.", snap) == []


def test_percent_matches_underlying_fraction():
    snap = {"savings_rate": 0.3104}
    assert check_grounding("Your savings rate is 31%.", snap) == []


def test_percent_matches_fraction_to_two_decimals():
    snap = {"savings_rate": 0.3104}
    assert check_grounding("Your savings rate is 31.04%.", snap) == []


def test_invented_number_is_reported():
    snap = {"total_value": 12400}
    ungrounded = check_grounding("You also received a PLN 999.00 bonus.", snap)
    assert ungrounded == ["999.00"]


def test_multiple_ungrounded_numbers_are_all_reported_once_each():
    snap = {"total_value": 100}
    text = "Figures of 55 and 55 and 77 appear nowhere in the data."
    ungrounded = check_grounding(text, snap)
    assert ungrounded == ["55", "77"]


def test_nested_snapshot_numbers_are_found():
    snap = {"holdings": [{"name": "Cash", "value": 3500.5}, {"name": "Gold", "value": 1200}]}
    assert check_grounding("Cash holds 3,500.50 and Gold holds 1,200.00.", snap) == []


def test_calendar_year_is_not_flagged_as_ungrounded():
    snap = {"total_value": 100}
    assert check_grounding("This is the 2026 digest.", snap) == []


def test_rounded_money_within_tolerance_matches():
    # 12400.37 rounds to 12,400.00 at 2dp on the way down, and the model is
    # allowed to have rounded rather than invented a number.
    snap = {"total_value": 12400.37}
    assert check_grounding("Total value is about PLN 12,400.00.", snap) == []
