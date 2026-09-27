"""Rounding helpers and year-parameter lookup.

These are the foundations everything else in the tax engine is built on: if
half-up rounding or the year fallback were wrong, every golden value in
test_uop.py / test_b2b.py would be wrong too, so they get their own direct
checks.
"""
from src.tax.pl.params import get_params, money, whole


def test_whole_rounds_half_up():
    assert whole(2.5) == 3


def test_money_rounds_half_up():
    assert money(0.125) == 0.13


def test_get_params_exact_year():
    assert get_params(2025).year == 2025
    assert get_params(2026).year == 2026


def test_get_params_future_year_reuses_latest():
    # No rules are legislated for a year that hasn't started; reusing 2026's
    # is an explicit, visible assumption rather than a guess.
    p = get_params(2027)
    assert p.year == 2026


def test_get_params_before_earliest_raises():
    import pytest

    with pytest.raises(ValueError):
        get_params(2024)


def test_health_min_monthly():
    assert get_params(2026).health_min_monthly == 432.54
    assert get_params(2025).health_min_monthly == 314.96


def test_voluntary_nfz_monthly():
    assert get_params(2026).voluntary_nfz_monthly == 830.58


def test_ikze_limits_follow_the_forecast_wage():
    """IKZE is 1.2x (1.8x for JDG) the forecast average wage of its year."""
    from src.tax.pl.params import get_params

    for year in (2025, 2026):
        p = get_params(year)
        assert p.ikze_limit == round(1.2 * p.avg_wage_forecast, 2)
        assert p.ikze_limit_jdg == round(1.8 * p.avg_wage_forecast, 2)
        assert p.ike_limit == round(3 * p.avg_wage_forecast, 2)
