"""Pure-Python FIRE (Financial Independence, Retire Early) maths.

Every amount here is real (today's money, inflation already stripped out)
and every rate is a real annual rate, so a figure computed today stays
comparable to one computed next year without re-deflating it. No DB, no
FastAPI, no tax engine - a later work package wires this to both, feeding it
a real income/spend figure that already has Polish tax and ZUS taken out.
"""
from __future__ import annotations

from dataclasses import dataclass

# Age at which each Polish tax-advantaged wrapper's money becomes accessible
# without penalty. IKZE is later than the other three, so it is deliberately
# excluded from the "accessible" bridge money everywhere below (see
# bridge_check) rather than averaged in with them.
ACCESS_AGE = {"ike": 60, "ppk": 60, "oipe": 60, "ikze": 65}

# The four ways to phrase "I no longer have to work". Kept as a tuple rather
# than re-listed in every function that needs all of them.
_VARIANTS = ("regular", "lean", "fat", "barista")


@dataclass
class FireAssumptions:
    """One person's numbers, in real terms, for every function below.

    Grouped into a dataclass rather than threaded as loose parameters
    because almost every function here needs most of these fields, and a
    dozen positional scalars is where a mismatched pair of ages or rates
    likes to hide.
    """

    current_age: float
    retirement_age: float  # statutory ZUS pension age
    target_fi_age: float | None
    swr: float  # safe withdrawal rate, e.g. 0.035
    real_return: float
    monthly_spend: float  # what life costs now
    monthly_net_income: float
    monthly_contribution: float  # what is actually saved per month
    fi_assets: float  # liquid assets counting toward FI (after reserve)
    accessible_assets: float  # part of fi_assets outside IKE/IKZE/PPK/OIPE
    zus_pension_monthly: float = 0.0
    barista_income_monthly: float = 0.0
    health_cost_monthly: float = 0.0  # voluntary NFZ while not working
    capital_gains_tax: float = 0.19
    gain_share: float = 0.5  # share of each withdrawal that is gain
    lean_factor: float = 0.8
    fat_factor: float = 1.5


def monthly_rate(annual: float) -> float:
    """Compounding monthly rate equivalent to an annual rate.

    (1+annual)**(1/12) - 1, not annual/12: every simulation below compounds
    monthly, so the monthly step has to compound back to exactly the annual
    figure rather than a linear approximation of it.
    """
    return (1 + annual) ** (1 / 12) - 1


def annuity_factor(r: float, years: float) -> float:
    """Present value, in years of payments, of 1/year for `years` years at rate r.

    r == 0 collapses to a plain sum (`years` itself) instead of dividing by
    zero, and a non-positive horizon has nothing left to fund.
    """
    if years <= 0:
        return 0.0
    if r == 0:
        return years
    return (1 - (1 + r) ** -years) / r


def gross_up(annual_net: float, cgt: float, gain_share: float) -> float:
    """Withdrawal needed before Belka tax to leave `annual_net` after it.

    Belka is charged only on the gain portion of a withdrawal from a taxable
    account, never on the return of principal, so only `gain_share` of the
    withdrawal is taxed at `cgt`.
    """
    return annual_net / (1 - cgt * gain_share)


def fi_target(
    annual_spend: float,
    pension_annual: float,
    swr: float,
    r: float,
    years_until_pension: float,
) -> float:
    """Portfolio needed to fund `annual_spend` for life, given a later pension.

    Two phases, because the portfolio's job changes the day the ZUS pension
    starts: before that day it funds everything, so that stretch is priced
    like a fixed-term annuity; after it, the portfolio only has to cover
    whatever the pension does not (`gap`), funded in perpetuity at `swr`.
    The portfolio never has to carry more than the pension actually
    provides during the bridge years, hence `bridge = min(pension, spend)`
    rather than the full spend.
    """
    gap = max(annual_spend - pension_annual, 0.0)
    bridge = min(pension_annual, annual_spend)
    years = max(years_until_pension, 0.0)
    return gap / swr + bridge * annuity_factor(r, years)


def annual_spend_for(a: FireAssumptions, variant: str) -> float:
    """Grossed-up annual withdrawal target for one FIRE variant.

    `regular`/`lean`/`fat` scale the same lifestyle by a factor. `barista`
    swaps in part-time income for cash but drops the health cost, not just
    shrinks it: a part-time contract in Poland carries its own NFZ
    registration, and that swap - not a smaller pot - is the whole point of
    a barista job in a Polish FIRE plan.
    """
    if variant == "regular":
        annual_net = 12 * (a.monthly_spend + a.health_cost_monthly)
    elif variant == "lean":
        annual_net = 12 * (a.monthly_spend * a.lean_factor + a.health_cost_monthly)
    elif variant == "fat":
        annual_net = 12 * (a.monthly_spend * a.fat_factor + a.health_cost_monthly)
    elif variant == "barista":
        annual_net = 12 * max(a.monthly_spend - a.barista_income_monthly, 0.0)
    else:
        raise ValueError(f"unknown FIRE variant: {variant!r}")
    return gross_up(annual_net, a.capital_gains_tax, a.gain_share)


def _regular_target(a: FireAssumptions, age: float, monthly_spend: float) -> float:
    """Regular-FIRE target at `age`, pricing a hypothetical spend level.

    Factored out of annual_spend_for/fi_target so simulate(), projection()
    and required_contribution() can ask "what if spend were X" without
    mutating the shared assumptions object just to price one scenario.
    """
    annual_net = 12 * (monthly_spend + a.health_cost_monthly)
    annual_spend = gross_up(annual_net, a.capital_gains_tax, a.gain_share)
    years_until_pension = a.retirement_age - age
    return fi_target(
        annual_spend, a.zus_pension_monthly * 12, a.swr, a.real_return, years_until_pension
    )


def targets_at(a: FireAssumptions, age: float) -> dict[str, float]:
    """FI number for each variant, evaluated as of `age`.

    Years until pension depends on the age being evaluated, not on
    a.current_age, so this same function prices "today" and "at the
    projected FI age" without a separate code path for either.
    """
    years_until_pension = a.retirement_age - age
    pension_annual = a.zus_pension_monthly * 12
    return {
        variant: fi_target(
            annual_spend_for(a, variant), pension_annual, a.swr, a.real_return, years_until_pension
        )
        for variant in _VARIANTS
    }


def coast(a: FireAssumptions) -> dict:
    """The "coast FI" number: stop contributing now, still retire on time.

    A pot of this size, left untouched to compound at real_return, grows
    into the full regular-FIRE number by retirement_age - so it is that
    future target discounted back to today at the same rate, not a target
    computed at today's age.
    """
    years = max(a.retirement_age - a.current_age, 0.0)
    future_target = fi_target(
        annual_spend_for(a, "regular"), a.zus_pension_monthly * 12, a.swr, a.real_return, 0
    )
    number = future_target / (1 + a.real_return) ** years
    return {"number": number, "reached": a.fi_assets >= number}


def simulate(
    a: FireAssumptions,
    *,
    monthly_contribution: float | None = None,
    monthly_spend: float | None = None,
    max_years: int = 60,
) -> dict:
    """Month-by-month portfolio growth until it can fund regular FIRE.

    Contribution and spend can be overridden so the same walk-forward
    answers "what if" questions (savings_rate_curve, levers) without a new
    FireAssumptions per scenario. Also stops past age 100 so a contribution
    too small to ever close the gap cannot spin the loop out to max_years
    for no useful answer.
    """
    contribution = a.monthly_contribution if monthly_contribution is None else monthly_contribution
    spend = a.monthly_spend if monthly_spend is None else monthly_spend
    i = monthly_rate(a.real_return)

    value = a.fi_assets
    age = a.current_age
    if value >= _regular_target(a, age, spend):
        return {"years": 0.0, "fi_age": age}

    for month in range(1, int(max_years * 12) + 1):
        value = value * (1 + i) + contribution
        age = a.current_age + month / 12
        if age > 100:
            return {"years": None, "fi_age": None}
        if value >= _regular_target(a, age, spend):
            return {"years": month / 12, "fi_age": age}
    return {"years": None, "fi_age": None}


def projection(a: FireAssumptions, years: float) -> list[dict]:
    """Yearly value-vs-target series for charting, continuing past FI.

    Unlike simulate(), this never stops early - a chart is more informative
    showing the portfolio keep growing past the target line than cutting
    off right at the crossing point.
    """
    i = monthly_rate(a.real_return)
    value = a.fi_assets
    out = [
        {
            "year_offset": 0,
            "age": a.current_age,
            "value": value,
            "target": _regular_target(a, a.current_age, a.monthly_spend),
        }
    ]
    n_months = int(round(max(years, 0) * 12))
    for month in range(1, n_months + 1):
        value = value * (1 + i) + a.monthly_contribution
        if month % 12 == 0:
            age = a.current_age + month / 12
            out.append(
                {
                    "year_offset": month // 12,
                    "age": age,
                    "value": value,
                    "target": _regular_target(a, age, a.monthly_spend),
                }
            )
    return out


def required_contribution(a: FireAssumptions, target_age: float) -> float | None:
    """Monthly saving that gets fi_assets to the regular target by `target_age`.

    Solves the level-payment growth annuity for the payment:
    PMT = (T - V0*(1+i)^n) * i / ((1+i)^n - 1). None rather than 0 when
    target_age is not strictly in the future - there is no schedule to
    solve for, and 0 would read as "you need to save nothing".
    """
    n = (target_age - a.current_age) * 12
    if n <= 0:
        return None
    i = monthly_rate(a.real_return)
    target = _regular_target(a, target_age, a.monthly_spend)
    v0 = a.fi_assets
    if i == 0:
        pmt = (target - v0) / n
    else:
        pmt = (target - v0 * (1 + i) ** n) * i / ((1 + i) ** n - 1)
    return max(pmt, 0.0)


def _value_at_age(a: FireAssumptions, age: float) -> float:
    """Portfolio value at `age` under steady contributions, no stopping rule.

    The closed-form twin of required_contribution's annuity: needed wherever
    a value is required at a specific age that was not necessarily the age
    simulate() would have stopped at on its own (e.g. a user-chosen
    target_fi_age).
    """
    n = (age - a.current_age) * 12
    if n <= 0:
        return a.fi_assets
    i = monthly_rate(a.real_return)
    if i == 0:
        return a.fi_assets + a.monthly_contribution * n
    return a.fi_assets * (1 + i) ** n + a.monthly_contribution * ((1 + i) ** n - 1) / i


def bridge_check(a: FireAssumptions, fi_age: float) -> dict:
    """Can accessible (non-IKE/IKZE/PPK/OIPE) money carry the gap to 60?

    IKZE unlocks at ACCESS_AGE["ikze"] (65), later than the other three
    wrappers, so it stays out of "accessible" everywhere and is simply
    noted here rather than assumed available at 60 like the rest.
    """
    bridge_target_age = ACCESS_AGE["ike"]
    bridge_years = max(bridge_target_age - fi_age, 0.0)
    annual_net = 12 * (a.monthly_spend + a.health_cost_monthly)
    annual_spend = gross_up(annual_net, a.capital_gains_tax, a.gain_share)
    needed = annual_spend * annuity_factor(a.real_return, bridge_years)

    accessible_share = 1.0 if a.fi_assets == 0 else a.accessible_assets / a.fi_assets
    projected_accessible = _value_at_age(a, fi_age) * accessible_share
    return {
        "needed": needed,
        "projected_accessible": projected_accessible,
        "ok": projected_accessible >= needed,
    }


def savings_rate_curve(a: FireAssumptions) -> list[dict]:
    """Years to FI against savings rate, holding income fixed.

    The chart that makes the point of the whole model: spend and
    contribution are two views of the same income, so sweeping the split
    between them shows savings rate - not the rate of return - as the lever
    that actually moves the FI date.
    """
    income = a.monthly_net_income
    if income <= 0:
        return []
    out = []
    for step in range(5, 81, 5):
        rate = step / 100
        spend = (1 - rate) * income
        contribution = rate * income
        years = simulate(a, monthly_contribution=contribution, monthly_spend=spend)["years"]
        out.append({"rate": rate, "years": years})
    return out


def levers(a: FireAssumptions, delta: float = 1000) -> dict:
    """How much sooner FI arrives from cutting spend vs. raising income.

    Cutting spend does double duty - the freed money becomes contribution
    too - while a raise of the same size only fills the contribution. The
    delta has to be identical on both sides for the comparison to be fair,
    which is exactly what shows cutting spend outrunning earning more.
    """
    baseline = simulate(a)["years"]

    cut_spend = max(a.monthly_spend - delta, 0.0)
    spend_cut_sim = simulate(
        a, monthly_spend=cut_spend, monthly_contribution=a.monthly_contribution + delta
    )
    income_raise_sim = simulate(a, monthly_contribution=a.monthly_contribution + delta)

    spend_cut_fi_number = (
        None
        if spend_cut_sim["fi_age"] is None
        else _regular_target(a, spend_cut_sim["fi_age"], cut_spend)
    )
    income_raise_fi_number = (
        None
        if income_raise_sim["fi_age"] is None
        else _regular_target(a, income_raise_sim["fi_age"], a.monthly_spend)
    )

    return {
        "baseline_years": baseline,
        "spend_cut": {"years": spend_cut_sim["years"], "fi_number": spend_cut_fi_number},
        "income_raise": {"years": income_raise_sim["years"], "fi_number": income_raise_fi_number},
    }


def compute(a: FireAssumptions) -> dict:
    """Bundles every FIRE view into one payload for the API layer.

    One entry point so the route calls a single function and every piece
    above stays independently testable. Rounding happens only here, on the
    way out, so each function above keeps full precision for whatever calls
    it next.
    """
    sim = simulate(a)
    fi_age = sim["fi_age"]

    targets_age = fi_age if fi_age is not None else (
        a.target_fi_age if a.target_fi_age is not None else a.current_age
    )
    targets = targets_at(a, targets_age)
    progress = a.fi_assets / targets["regular"] if targets["regular"] else None

    coast_result = coast(a)

    required = None
    if a.target_fi_age is not None:
        contribution = required_contribution(a, a.target_fi_age)
        savings_rate = (
            contribution / a.monthly_net_income
            if contribution is not None and a.monthly_net_income
            else None
        )
        required_net_income = (
            a.monthly_spend + contribution if contribution is not None else None
        )
        required = {
            "contribution": contribution,
            "savings_rate": savings_rate,
            "required_net_income": required_net_income,
        }

    current_savings_rate = (
        a.monthly_contribution / a.monthly_net_income if a.monthly_net_income else None
    )

    bridge_age = fi_age if fi_age is not None else a.target_fi_age
    bridge = bridge_check(a, bridge_age) if bridge_age is not None else None

    curve = savings_rate_curve(a)
    lever_result = levers(a)

    horizon_candidates = [age for age in (fi_age, a.target_fi_age) if age is not None]
    horizon_age = (max(horizon_candidates) if horizon_candidates else a.current_age) + 5
    horizon_age = min(horizon_age, 100)
    proj = projection(a, max(horizon_age - a.current_age, 0))

    def money(v):
        return None if v is None else round(v, 2)

    def rate(v):
        return None if v is None else round(v, 4)

    def yrs(v):
        return None if v is None else round(v, 1)

    # The target moves with age (the pension bridge shortens), so the payload
    # says which age `targets` and `progress` are priced at, and carries the
    # "if you stopped today" figure next to it.
    targets_now = targets_at(a, a.current_age)
    return {
        "targets_age": yrs(targets_age),
        "targets": {k: money(v) for k, v in targets.items()},
        "targets_now": {k: money(v) for k, v in targets_now.items()},
        "progress": rate(progress),
        "coast": {"number": money(coast_result["number"]), "reached": coast_result["reached"]},
        "simulate": {"years": yrs(sim["years"]), "fi_age": yrs(sim["fi_age"])},
        "required": None
        if required is None
        else {
            "contribution": money(required["contribution"]),
            "savings_rate": rate(required["savings_rate"]),
            "required_net_income": money(required["required_net_income"]),
        },
        "current_savings_rate": rate(current_savings_rate),
        "bridge_check": None
        if bridge is None
        else {
            "needed": money(bridge["needed"]),
            "projected_accessible": money(bridge["projected_accessible"]),
            "ok": bridge["ok"],
        },
        "savings_rate_curve": [
            {"rate": rate(pt["rate"]), "years": yrs(pt["years"])} for pt in curve
        ],
        "levers": {
            "baseline_years": yrs(lever_result["baseline_years"]),
            "spend_cut": {
                "years": yrs(lever_result["spend_cut"]["years"]),
                "fi_number": money(lever_result["spend_cut"]["fi_number"]),
            },
            "income_raise": {
                "years": yrs(lever_result["income_raise"]["years"]),
                "fi_number": money(lever_result["income_raise"]["fi_number"]),
            },
        },
        "projection": [
            {
                "year_offset": p["year_offset"],
                "age": yrs(p["age"]),
                "value": money(p["value"]),
                "target": money(p["target"]),
            }
            for p in proj
        ],
    }
