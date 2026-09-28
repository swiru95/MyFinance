"""Blended portfolio return, ported from frontend/src/lib/projection.ts.

Kept in Python too because the FIRE maths (fire.py) needs the same blended
rate the frontend projection chart uses, and the two must never quietly
drift into different numbers for the same portfolio.
"""
from __future__ import annotations

# Expected nominal annual returns, in PLN, used to project the portfolio.
#
# These are long-run averages for the asset class, not forecasts, and they
# are the only guessed input in the projection - the contribution side comes
# from what the user actually recorded. Deliberately conservative: a
# projection is most useful when it under-promises.
#
# Crypto is 0%. It is not an oversight and it is not a claim that crypto goes
# nowhere: it is a refusal to put a number on something whose dispersion is
# wider than the projection horizon. With a fifth of a portfolio in it, any
# rate picked here would dominate the chart while being indistinguishable
# from a wish.
#
# Receivables are 0% because a holding valued by kind="interest" already
# accrues statutory interest on the server; growing it again here would
# count the same interest twice.
CATEGORY_RETURNS: dict[str, float] = {
    "Cash": 0.02,
    "Savings": 0.04,
    "Bonds": 0.05,
    "TFI": 0.06,
    "Retirement": 0.06,
    "Stocks": 0.08,
    "Gold": 0.03,
    # Silver/platinum/palladium: same rate as Gold (see profiles.py - they
    # share its risk band too), rather than inventing a separate guess for
    # three metals with no more forecastability than gold has.
    "Metals": 0.03,
    "Crypto": 0,
    "Watches": 0,
    "Fixed Assets": 0,
    "Receivables": 0,
}

# Fallback for a class the table above does not name - a category the user
# typed themselves. Every asset carries a risk band, so that answers it
# without inventing a rate for a name nobody has seen before.
PROFILE_RETURNS: dict[str, float] = {
    "safe": 0.03,
    "moderate": 0.05,
    "risky": 0.07,
    "illiquid": 0,
}


def blended_nominal_return(items: list[dict]) -> float:
    """Value-weighted nominal return across a set of holdings.

    Mirrors blendedRate() in projection.ts but works from a flat list rather
    than an Allocation, since the FIRE inputs come from a wallet snapshot,
    not the allocation endpoint. Falls back to the holding's risk profile
    when its category is not one of the named asset classes, and to 0 when
    neither is known - the same "unknown gets nothing invented" rule the
    frontend table uses.
    """
    total = sum(item.get("value", 0.0) for item in items)
    if total <= 0:
        return 0.0

    blended = 0.0
    for item in items:
        value = item.get("value", 0.0)
        category = item.get("category")
        profile = item.get("profile")
        rate = CATEGORY_RETURNS.get(category, PROFILE_RETURNS.get(profile, 0.0))
        blended += (value / total) * rate
    return blended


def real_rate(nominal: float, inflation: float) -> float:
    """Nominal return deflated by inflation, Fisher-style.

    (1+nominal)/(1+inflation) - 1 rather than a plain subtraction: the
    subtraction only approximates compounding and drifts further from the
    true figure the higher the rates involved, which matters at Polish
    inflation levels.
    """
    return (1 + nominal) / (1 + inflation) - 1
