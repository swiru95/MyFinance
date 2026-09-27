"""FIRE maths: annuity/target formulas in isolation, then the walk-forward
simulation and the derived views (curve, levers, bridge, compute) built on top
of them.
"""
from __future__ import annotations

import math

import pytest

from src.services import fire


def _assumptions(**overrides) -> fire.FireAssumptions:
    """A complete, reasonable set of assumptions with every field overridable.

    Centralised so each test only states the handful of fields it actually
    cares about instead of repeating all seventeen dataclass fields.
    """
    defaults = dict(
        current_age=30.0,
        retirement_age=65.0,
        target_fi_age=None,
        swr=0.035,
        real_return=0.04,
        monthly_spend=5000.0,
        monthly_net_income=10000.0,
        monthly_contribution=3000.0,
        fi_assets=100_000.0,
        accessible_assets=100_000.0,
    )
    defaults.update(overrides)
    return fire.FireAssumptions(**defaults)


# --- annuity_factor -------------------------------------------------------


def test_annuity_factor_zero_rate_is_a_plain_sum():
    assert fire.annuity_factor(0, 10) == 10


def test_annuity_factor_zero_years_funds_nothing():
    assert fire.annuity_factor(0.03, 0) == 0


# --- fi_target -------------------------------------------------------------


def test_fi_target_no_pension_is_swr_perpetuity():
    assert fire.fi_target(40_000, 0, 0.04, 0.03, 0) == 1_000_000


def test_fi_target_with_pension_bridge_adds_to_the_perpetuity():
    # gap = 40_000 - 20_000 = 20_000 -> 500_000 at 4% SWR.
    # bridge = min(20_000, 40_000) = 20_000 for 10 flat years -> 200_000.
    assert fire.fi_target(40_000, 20_000, 0.04, 0, 10) == 500_000 + 200_000


def test_fi_target_pension_covering_spend_is_just_the_bridge():
    # Pension exceeds spend: gap is 0, so the whole target is the bridge
    # years the portfolio has to cover before the (ample) pension starts.
    target = fire.fi_target(30_000, 40_000, 0.04, 0, 5)
    assert target == pytest.approx(30_000 * 5)


# --- gross_up ----------------------------------------------------------------


def test_gross_up_grosses_up_only_the_gain_share():
    assert fire.gross_up(81_450, 0.19, 0.5) == pytest.approx(90_000, rel=1e-6)


def test_gross_up_no_tax_is_a_no_op():
    assert fire.gross_up(50_000, 0, 0.5) == 50_000


# --- simulate ----------------------------------------------------------------


def test_simulate_already_fi_is_zero_years():
    a = _assumptions(fi_assets=50_000_000, monthly_contribution=0)
    result = fire.simulate(a)
    assert result == {"years": 0.0, "fi_age": a.current_age}


def test_simulate_flat_rate_matches_hand_computed_months():
    # swr 0.1, monthly_spend 1_000, no pension/health/tax => regular annual
    # target = 12_000 / 0.1 = 120_000 exactly, independent of ages. With
    # r = 0 and a flat 1_000/month contribution from V0 = 0, that takes
    # exactly 120 months.
    a = _assumptions(
        real_return=0,
        swr=0.1,
        monthly_spend=1000,
        capital_gains_tax=0,
        fi_assets=0,
        monthly_contribution=1000,
    )
    result = fire.simulate(a)
    assert result["years"] == pytest.approx(10.0)


def test_simulate_never_reaching_target_within_the_horizon_is_none():
    # A contribution too small to ever close a large gap at a low return.
    a = _assumptions(
        current_age=30,
        real_return=0.01,
        swr=0.03,
        monthly_spend=20_000,
        monthly_contribution=10,
        fi_assets=0,
    )
    result = fire.simulate(a, max_years=60)
    assert result == {"years": None, "fi_age": None}


# --- required_contribution ----------------------------------------------------


def test_required_contribution_flat_rate_equals_straight_line_pmt():
    a = _assumptions(real_return=0, fi_assets=50_000, current_age=30, retirement_age=65)
    target_age = 40.0

    # T recomputed independently via the public fi_target/gross_up, not by
    # reaching into required_contribution's own machinery.
    annual_net = 12 * (a.monthly_spend + a.health_cost_monthly)
    annual_spend = fire.gross_up(annual_net, a.capital_gains_tax, a.gain_share)
    years_until_pension = a.retirement_age - target_age
    target = fire.fi_target(
        annual_spend, a.zus_pension_monthly * 12, a.swr, a.real_return, years_until_pension
    )
    n = (target_age - a.current_age) * 12
    expected = max((target - a.fi_assets) / n, 0.0)

    assert fire.required_contribution(a, target_age) == pytest.approx(expected)


def test_required_contribution_past_or_present_target_age_is_none():
    a = _assumptions(current_age=40)
    assert fire.required_contribution(a, 40) is None
    assert fire.required_contribution(a, 35) is None


# --- savings_rate_curve --------------------------------------------------------


def test_savings_rate_curve_years_are_non_increasing_in_rate():
    a = _assumptions(
        monthly_net_income=10_000,
        current_age=30,
        retirement_age=65,
        real_return=0.05,
        swr=0.04,
        fi_assets=0,
    )
    curve = fire.savings_rate_curve(a)
    assert [pt["rate"] for pt in curve] == [round(s / 100, 2) for s in range(5, 81, 5)]

    # None means "never within the horizon", i.e. worse than any finite
    # figure, so it sorts as +inf for the monotonicity check.
    as_orderable = [math.inf if pt["years"] is None else pt["years"] for pt in curve]
    assert all(a1 >= a2 for a1, a2 in zip(as_orderable, as_orderable[1:]))


def test_savings_rate_curve_is_empty_without_income():
    a = _assumptions(monthly_net_income=0)
    assert fire.savings_rate_curve(a) == []


# --- levers --------------------------------------------------------------------


def test_levers_spend_cut_beats_or_matches_income_raise():
    a = _assumptions(
        current_age=30,
        retirement_age=65,
        real_return=0.04,
        swr=0.035,
        monthly_spend=6000,
        monthly_contribution=2000,
        fi_assets=50_000,
    )
    result = fire.levers(a, delta=1000)

    spend_cut_years = result["spend_cut"]["years"]
    income_raise_years = result["income_raise"]["years"]
    key = lambda v: math.inf if v is None else v
    assert key(spend_cut_years) <= key(income_raise_years)


# --- real_rate / blended return already covered in test_returns.py -----------


# --- coast, bridge_check, targets_at, compute: smoke + shape ------------------


def test_coast_number_matches_discounted_future_target():
    a = _assumptions(current_age=40, retirement_age=65, real_return=0.03)
    result = fire.coast(a)
    future_target = fire.fi_target(
        fire.annual_spend_for(a, "regular"), a.zus_pension_monthly * 12, a.swr, a.real_return, 0
    )
    expected = future_target / (1 + a.real_return) ** (a.retirement_age - a.current_age)
    assert result["number"] == pytest.approx(expected)
    assert result["reached"] == (a.fi_assets >= expected)


def test_targets_at_returns_all_four_variants_ordered_fat_ge_regular_ge_lean():
    a = _assumptions()
    targets = fire.targets_at(a, a.current_age)
    assert set(targets) == {"regular", "lean", "fat", "barista"}
    assert targets["fat"] >= targets["regular"] >= targets["lean"]


def test_bridge_check_is_free_once_past_the_ike_access_age():
    a = _assumptions()
    result = fire.bridge_check(a, fire.ACCESS_AGE["ike"])
    assert result["needed"] == 0
    assert result["ok"] is True


def test_bridge_check_before_60_needs_a_positive_bridge():
    a = _assumptions(current_age=45, accessible_assets=0, fi_assets=100_000)
    result = fire.bridge_check(a, 50)
    assert result["needed"] > 0
    # No accessible assets at all -> cannot possibly cover the bridge.
    assert result["projected_accessible"] == 0
    assert result["ok"] is False


def test_compute_smoke_has_the_documented_shape():
    a = _assumptions(target_fi_age=50)
    result = fire.compute(a)
    assert set(result) == {
        "targets_age",
        "targets",
        "targets_now",
        "progress",
        "coast",
        "simulate",
        "required",
        "current_savings_rate",
        "bridge_check",
        "savings_rate_curve",
        "levers",
        "projection",
    }
    assert result["required"] is not None
    assert result["bridge_check"] is not None
    assert len(result["savings_rate_curve"]) == 16
    # Rounded to 2dp in the output, per spec, even though intermediate values
    # carry full precision.
    for v in result["targets"].values():
        assert round(v, 2) == v


def test_compute_without_target_fi_age_has_no_required_block():
    a = _assumptions(target_fi_age=None)
    result = fire.compute(a)
    assert result["required"] is None
