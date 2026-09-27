"""Blended-return maths: value-weighting, category/profile fallback, Fisher deflation."""
from __future__ import annotations

import pytest

from src.services import returns


def test_blended_nominal_return_weights_by_value():
    # Two known categories, unevenly sized: the blend must be value-weighted,
    # not a plain average of the two rates (which would be 0.05).
    items = [
        {"category": "Cash", "profile": "safe", "value": 8000},  # rate 0.02
        {"category": "Stocks", "profile": "risky", "value": 2000},  # rate 0.08
    ]
    expected = 0.8 * returns.CATEGORY_RETURNS["Cash"] + 0.2 * returns.CATEGORY_RETURNS["Stocks"]
    assert returns.blended_nominal_return(items) == pytest.approx(expected)


def test_blended_nominal_return_falls_back_to_profile():
    # "Vintage Cars" is not in CATEGORY_RETURNS, so it must fall back to the
    # profile rate rather than being silently dropped or treated as 0.
    items = [{"category": "Vintage Cars", "profile": "moderate", "value": 1000}]
    assert returns.blended_nominal_return(items) == pytest.approx(
        returns.PROFILE_RETURNS["moderate"]
    )


def test_blended_nominal_return_unknown_category_and_profile_is_zero():
    items = [{"category": "Mystery", "profile": "unheard-of", "value": 1000}]
    assert returns.blended_nominal_return(items) == 0.0


def test_blended_nominal_return_empty_or_worthless_portfolio():
    assert returns.blended_nominal_return([]) == 0.0
    assert returns.blended_nominal_return([{"category": "Cash", "value": 0}]) == 0.0


def test_real_rate_matches_fisher_equation():
    assert returns.real_rate(0.08, 0.035) == pytest.approx(0.04348, abs=1e-5)


def test_real_rate_zero_inflation_is_the_nominal_rate():
    assert returns.real_rate(0.06, 0) == pytest.approx(0.06)
