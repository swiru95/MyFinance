"""Side-by-side umowa o pracę vs. JDG (B2B), the question people actually
ask when they consider switching: "what would I need to bill to end up
where I am now, and what does that cost my pension?"
"""
from __future__ import annotations

from .b2b import B2bOptions, b2b_schedule
from .params import money
from .reverse import _bisect
from .uop import UopOptions, uop_schedule


def compare_uop_b2b(
    year: int,
    uop_gross_monthly: float,
    uop_opts: UopOptions,
    b2b_revenue_monthly: float,
    b2b_costs_monthly: float,
    b2b_opts: B2bOptions,
    *,
    paid_leave_days: int = 26,
    working_days: int = 250,
    b2b_billed_per_day: bool = True,
) -> dict:
    uop_year = uop_schedule(year, [uop_gross_monthly] * 12, uop_opts)

    # A contractor doesn't get paid for a day off; an employee does. Modelling
    # that as a flat scale-down of every month's revenue is a simplification
    # (real unpaid leave clusters, doesn't spread evenly) but it is the right
    # simplification for an annual comparison rather than a cash-flow one.
    leave_factor = (
        (working_days - paid_leave_days) / working_days if b2b_billed_per_day else 1.0
    )
    b2b_costs = [b2b_costs_monthly] * 12
    b2b_revenue_scaled = [b2b_revenue_monthly * leave_factor] * 12
    b2b_year = b2b_schedule(year, b2b_revenue_scaled, b2b_costs, b2b_opts)

    uop_annual_net = uop_year.totals["net"]

    def take_home_at(revenue_before_leave: float) -> float:
        scaled = [revenue_before_leave * leave_factor] * 12
        return b2b_schedule(year, scaled, b2b_costs, b2b_opts).totals["take_home"]

    equivalent_revenue = _bisect(
        take_home_at, uop_annual_net, hi=max(uop_annual_net * 2, 12_000.0)
    )

    pension_gap_annual = money(
        uop_year.pension_account_contributions - b2b_year.pension_account_contributions
    )
    difference_net_annual = money(b2b_year.totals["take_home"] - uop_annual_net)

    return {
        "year": year,
        "uop_gross_monthly": uop_gross_monthly,
        "b2b_revenue_monthly": b2b_revenue_monthly,
        "b2b_costs_monthly": b2b_costs_monthly,
        "paid_leave_days": paid_leave_days,
        "working_days": working_days,
        "b2b_billed_per_day": b2b_billed_per_day,
        "uop_annual_net": money(uop_annual_net),
        "uop_employer_cost_annual": money(uop_year.totals["employer_cost"]),
        "uop_pension_account_contributions": uop_year.pension_account_contributions,
        "b2b_annual_revenue": money(b2b_year.totals["revenue"]),
        "b2b_annual_take_home": money(b2b_year.totals["take_home"]),
        "b2b_pension_account_contributions": b2b_year.pension_account_contributions,
        "b2b_equivalent_revenue_monthly": money(equivalent_revenue),
        "pension_gap_annual": pension_gap_annual,
        "difference_net_annual": difference_net_annual,
    }
