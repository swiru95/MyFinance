"""XIRR: the annualised, money-weighted return of a set of dated cash flows.

Used only for the PDF report's one summary "annualised return" figure (see
services/efficiency.py) - everything else in the app reports plain growth_pct
(services/growth.py), which does not annualise or account for *when* within
the period money moved. XIRR is the standard way to fold both of those in:
find the constant annual rate `r` that discounts every cash flow (deposits
as negative, withdrawals and the closing value as positive) back to a net
present value of zero.

Solved by bisection rather than Newton's method: the derivative-free version
needs no special-casing near a zero derivative, and a bracketed root is easy
to certify (the two ends disagree in sign) rather than trusted on faith the
way an unbracketed Newton iteration would be.
"""
from __future__ import annotations

from datetime import date

# -99.99% to +10,000% annualised - wide enough for any real portfolio result
# without letting a runaway bisection report a meaningless extreme.
_LO, _HI = -0.9999, 100.0
_ITERATIONS = 100
_DAYS_PER_YEAR = 365.0


def _npv(rate: float, cashflows: list[tuple[date, float]], d0: date) -> float:
    total = 0.0
    for d, amount in cashflows:
        years = (d - d0).days / _DAYS_PER_YEAR
        total += amount / (1.0 + rate) ** years
    return total


def xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """The annualised rate solving the cash flows' NPV to zero, or None when
    there is nothing to solve for: fewer than two flows, or every flow the
    same sign (money only ever moved one way, so no rate answers "what did
    it earn"). Returns None rather than a number bisection could not have
    found reliably when the two ends of the search range do not bracket a
    sign change either - that can happen for a cash-flow pattern where net
    present value is not monotonic in the rate, which a real portfolio's
    deposit-then-grow flows essentially never produce, but a synthetic or
    malformed input might.
    """
    if len(cashflows) < 2:
        return None
    if not any(a < 0 for _, a in cashflows) or not any(a > 0 for _, a in cashflows):
        return None

    d0 = min(d for d, _ in cashflows)
    lo, hi = _LO, _HI
    npv_lo, npv_hi = _npv(lo, cashflows, d0), _npv(hi, cashflows, d0)
    if npv_lo == 0:
        return lo
    if npv_hi == 0:
        return hi
    if (npv_lo > 0) == (npv_hi > 0):
        return None

    mid = lo
    for _ in range(_ITERATIONS):
        mid = (lo + hi) / 2.0
        npv_mid = _npv(mid, cashflows, d0)
        if npv_mid == 0:
            return mid
        if (npv_mid > 0) == (npv_lo > 0):
            lo, npv_lo = mid, npv_mid
        else:
            hi, npv_hi = mid, npv_mid
    return (lo + hi) / 2.0
