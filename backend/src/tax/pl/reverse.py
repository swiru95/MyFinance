"""Solve for the gross/revenue that produces a target take-home.

People plan from "I need X in my pocket," not from a gross figure, so this
inverts the forward schedules. Bisection rather than an algebraic inverse
because the forward maths has thresholds (the ZUS cap, the 120k PIT
threshold, the ryczałt tiers) that make it piecewise, not a single formula.
"""
from __future__ import annotations

from .b2b import B2bOptions, b2b_schedule
from .params import money
from .uop import UopOptions, uop_schedule


def _bisect(f, target: float, lo: float = 0.0, hi: float = 1_000.0,
            tol: float = 0.5, max_iter: int = 100) -> float:
    """Smallest x with f(x) within `tol` of `target`, assuming f is
    non-decreasing. Doubles `hi` first so the caller never has to guess a
    range that is big enough for the target it was given."""
    expansions = 0
    while f(hi) < target and expansions < 60:
        hi *= 2
        expansions += 1

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        val = f(mid)
        if abs(val - target) <= tol:
            return mid
        if val < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def reverse_uop(year: int, target_net_monthly: float, opts: UopOptions) -> dict:
    """Constant monthly gross whose average net over the year hits the target."""
    if target_net_monthly <= 0:
        result = uop_schedule(year, [0.0] * 12, opts)
        d = result.to_dict()
        d.pop("months", None)
        return {"gross_monthly": 0.0, "achieved_net_monthly": 0.0, "year": d}

    def net_at(gross: float) -> float:
        return uop_schedule(year, [gross] * 12, opts).totals["net"] / 12

    gross = _bisect(net_at, target_net_monthly, hi=max(target_net_monthly * 2, 1_000.0))
    achieved = net_at(gross)
    result = uop_schedule(year, [gross] * 12, opts)
    d = result.to_dict()
    d.pop("months", None)
    return {
        "gross_monthly": money(gross),
        "achieved_net_monthly": money(achieved),
        "year": d,
    }


def reverse_b2b(
    year: int, target_take_home_monthly: float, costs_monthly: float, opts: B2bOptions
) -> dict:
    """Constant monthly revenue whose average take-home over the year hits
    the target, given a fixed monthly cost."""
    if target_take_home_monthly <= 0:
        result = b2b_schedule(year, [0.0] * 12, [costs_monthly] * 12, opts)
        d = result.to_dict()
        d.pop("months", None)
        return {"revenue_monthly": 0.0, "achieved_take_home_monthly": 0.0, "year": d}

    costs = [costs_monthly] * 12

    def take_home_at(revenue: float) -> float:
        return b2b_schedule(year, [revenue] * 12, costs, opts).totals["take_home"] / 12

    revenue = _bisect(
        take_home_at, target_take_home_monthly, hi=max(target_take_home_monthly * 2, 1_000.0)
    )
    achieved = take_home_at(revenue)
    result = b2b_schedule(year, [revenue] * 12, costs, opts)
    d = result.to_dict()
    d.pop("months", None)
    return {
        "revenue_monthly": money(revenue),
        "achieved_take_home_monthly": money(achieved),
        "year": d,
    }
