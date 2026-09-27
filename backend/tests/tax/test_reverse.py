"""Bisection inversion: given the target net/take-home, recover the gross."""
from src.tax.pl.b2b import B2bOptions, b2b_schedule
from src.tax.pl.reverse import reverse_b2b, reverse_uop
from src.tax.pl.uop import UopOptions


def test_reverse_uop_matches_forward_golden_value():
    opts = UopOptions(ppk_employee=0.0, ppk_employer=0.0)
    result = reverse_uop(2026, 7147.39, opts)
    assert abs(result["gross_monthly"] - 10_000.0) <= 1.0


def test_reverse_uop_nonpositive_target_is_zero():
    result = reverse_uop(2026, 0.0, UopOptions())
    assert result["gross_monthly"] == 0.0
    assert result["achieved_net_monthly"] == 0.0
    assert "months" not in result["year"]


def test_reverse_b2b_round_trips_through_forward():
    opts = B2bOptions(tax_form="liniowy", zus_stage="full", vat="standard")
    # Not the golden month-1 figure itself: liniowy's cumulative PIT advance
    # drifts a little from month to month even at constant revenue (rounding
    # of a running total, not a flat monthly rate), so the *average* take-home
    # at revenue 20 000 is close to but not exactly the month-1 value. Solve
    # forward first so the round trip is checked against a value the function
    # itself produces, not a figure only exact for a single month.
    forward = b2b_schedule(2026, [20_000.0] * 12, [0.0] * 12, opts)
    target = forward.totals["take_home"] / 12

    result = reverse_b2b(2026, target, 0.0, opts)
    assert abs(result["achieved_take_home_monthly"] - target) <= 0.5
    assert abs(result["revenue_monthly"] - 20_000.0) <= 5.0
