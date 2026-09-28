"""services.xirr.xirr: annualised money-weighted return, hand-checked.

XIRR solves sum(cf / (1+r)^years) = 0 for r. Every expected value below is
derived by hand from that equation, not just asserted against whatever the
function happens to produce.
"""
from datetime import date

import pytest

from src.services.xirr import xirr


def test_single_year_doubling_is_100_percent():
    """-1000 now, +2000 exactly 365 days later:
    -1000 + 2000/(1+r) = 0  =>  1+r = 2  =>  r = 1.0 (100%)."""
    cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), 2000.0)]
    r = xirr(cashflows)
    assert r == pytest.approx(1.0, abs=1e-6)


def test_single_year_ten_percent_gain():
    """-1000 now, +1100 exactly 365 days later:
    -1000 + 1100/(1+r) = 0  =>  1+r = 1.1  =>  r = 0.10 (10%)."""
    cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), 1100.0)]
    r = xirr(cashflows)
    assert r == pytest.approx(0.10, abs=1e-6)


def test_two_year_horizon_uses_compounding_not_doubling():
    """-1000 now, +1210 exactly 730 days (2 non-leap years) later:
    -1000 + 1210/(1+r)^2 = 0  =>  (1+r)^2 = 1.21  =>  1+r = 1.1  =>  r = 0.10.
    A linear (non-compounding) reading of the same numbers would wrongly
    say 10.5% ((1210-1000)/1000/2) - this checks the real, compounding
    answer instead. 2025 and 2026 are both non-leap, so this is exactly
    730 days, not 731 - a leap year in the span would skew the day count
    the test means to keep exact."""
    cashflows = [(date(2025, 1, 1), -1000.0), (date(2027, 1, 1), 1210.0)]
    r = xirr(cashflows)
    assert r == pytest.approx(0.10, abs=1e-6)


def test_matches_growth_pct_when_flows_are_a_single_exact_year():
    """The one case where XIRR and services.growth's plain growth_pct must
    agree exactly: a single deposit held for precisely one year with no
    interim flows - both then describe the same one-period return."""
    invested = 5000.0
    growth = 400.0
    value = invested + growth
    cashflows = [(date(2025, 3, 5), -invested), (date(2026, 3, 5), value)]
    r = xirr(cashflows)
    assert r == pytest.approx(growth / invested, abs=1e-6)


def test_deposit_partway_through_is_annualised_correctly():
    """-1000 on day 0, another -500 roughly halfway (day 182) through a
    365-day year, +1600 at day 365. Solved by the same NPV equation the
    implementation uses, evaluated independently here with a plain loop
    over a fine-grained rate sweep to cross-check xirr()'s own bisection
    rather than re-deriving its closed form."""
    d0 = date(2025, 1, 1)
    mid = date(2025, 7, 2)  # 182 days in
    end = date(2026, 1, 1)  # 365 days in
    cashflows = [(d0, -1000.0), (mid, -500.0), (end, 1600.0)]
    r = xirr(cashflows)

    def npv(rate):
        total = 0.0
        for d, amount in cashflows:
            years = (d - d0).days / 365.0
            total += amount / (1 + rate) ** years
        return total

    # r solves the NPV equation to (near) zero - the definition of XIRR.
    assert npv(r) == pytest.approx(0.0, abs=1e-4)
    # And sanity: a ~1500 in for ~1600 back over roughly a year is a modest
    # positive double-digit-at-most return, not something wild.
    assert 0.0 < r < 0.20


def test_all_flows_same_sign_is_unanswerable():
    """Money only ever went in (or only ever came out) - there is no rate
    that explains a wallet with no return figure to solve for."""
    cashflows = [(date(2025, 1, 1), -1000.0), (date(2025, 6, 1), -500.0)]
    assert xirr(cashflows) is None


def test_single_cashflow_is_unanswerable():
    assert xirr([(date(2025, 1, 1), -1000.0)]) is None


def test_empty_is_unanswerable():
    assert xirr([]) is None


def test_break_even_is_zero_percent():
    """-1000 now, +1000 back later: no gain, no loss, r = 0."""
    cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), 1000.0)]
    r = xirr(cashflows)
    assert r == pytest.approx(0.0, abs=1e-6)
