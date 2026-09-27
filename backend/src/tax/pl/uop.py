"""Umowa o pracę (employment contract) payroll, month by month.

Everything here is year-to-date cumulative because Polish withholding law is:
the ZUS 30x cap, the 120 000 PIT threshold and the "ulga dla młodych" annual
limit only make sense against a running total, not a single month looked at
in isolation. A schedule is always computed for all 12 months together so
that total can accumulate correctly even when pay varies month to month.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .params import get_params, money, round_floats, sum_fields, whole


@dataclass(frozen=True)
class UopOptions:
    kup: str = "standard"  # standard | commuting
    creative_share: float = 0.0  # 0..1, share of pay under 50% KUP
    pit2: bool = True  # monthly 300 PLN reduction (PIT-2 on file)
    young_relief: bool = False  # ulga dla młodych (under 26)
    ppk_employee: float = 0.02
    ppk_employee_extra: float = 0.0
    ppk_employer: float = 0.015
    ppk_employer_extra: float = 0.0
    accident_rate: float = 0.0167  # varies by employer risk class


@dataclass
class UopMonth:
    month: int
    gross: float
    pension: float
    disability: float
    sickness: float
    employee_social: float
    health: float
    kup: float
    pit_base: float
    pit_advance: float
    ppk_employee: float
    ppk_employer: float
    net: float
    employer_pension: float
    employer_disability: float
    employer_accident: float
    employer_fp: float
    employer_fgsp: float
    employer_cost: float
    zus_capped: bool
    over_threshold: bool

    def to_dict(self) -> dict:
        return round_floats(dataclasses.asdict(self))


@dataclass
class UopYear:
    params_year: int
    months: list[UopMonth]
    totals: dict
    annual_pit: float
    settlement: float  # positive = to pay in April, negative = refund
    effective_rate: float | None
    pension_account_contributions: float

    def to_dict(self) -> dict:
        return round_floats(dataclasses.asdict(self))


def uop_schedule(year: int, gross_by_month: list[float], opts: UopOptions) -> UopYear:
    p = get_params(year)
    if len(gross_by_month) != 12:
        raise ValueError("gross_by_month must have exactly 12 entries")

    months: list[UopMonth] = []
    ytd_zus_base = 0.0  # pension+disability base, capped at the 30x limit
    ytd_pit_base = 0.0  # for splitting each month across the 120k threshold
    ytd_kup_creative = 0.0
    ytd_exempt = 0.0  # young-relief exemption used so far this year

    for i, gross in enumerate(gross_by_month):
        month = i + 1

        # 1-2. ZUS base and employee contributions.
        remaining_cap = max(0.0, p.zus_annual_cap - ytd_zus_base)
        capped_base = min(gross, remaining_cap)
        zus_capped = capped_base < gross
        ytd_zus_base += capped_base

        pension = money(p.employee_pension_rate * capped_base)
        disability = money(p.employee_disability_rate * capped_base)
        sickness = money(p.employee_sickness_rate * gross)  # not capped
        employee_social = money(pension + disability + sickness)

        # 3. Health.
        health = money(p.employee_health_rate * (gross - employee_social))

        # 4. PPK - employer's share is the employee's taxable revenue.
        ppk_employer_amount = money(
            (opts.ppk_employer + opts.ppk_employer_extra) * gross
        )
        ppk_employee_amount = money(
            (opts.ppk_employee + opts.ppk_employee_extra) * gross
        )

        # 5. KUP (cost-of-obtaining-revenue deduction).
        if gross == 0:
            kup = 0.0
        else:
            income_after_social = gross - employee_social
            creative_part = opts.creative_share * income_after_social
            kup_creative_raw = 0.5 * creative_part
            remaining_creative_limit = max(
                0.0, p.kup_creative_annual_limit - ytd_kup_creative
            )
            kup_creative = min(kup_creative_raw, remaining_creative_limit)
            ytd_kup_creative += kup_creative

            non_creative_part = max(0.0, income_after_social - creative_part)
            standard_amount = (
                p.kup_monthly_commuting if opts.kup == "commuting" else p.kup_monthly
            )
            kup_standard = min(standard_amount, non_creative_part)
            kup = money(kup_creative + kup_standard)

        # 6. Young relief: exempt part of this month's revenue (gross plus
        # the employer PPK top-up, which is also taxable revenue), capped at
        # the annual limit. Social and KUP are only real deductions against
        # the *taxable* slice, so they are prorated for the PIT base below -
        # the actual ZUS/KUP amounts withheld are unaffected, because ulga
        # dla młodych exempts income from PIT, not from social insurance.
        revenue = gross + ppk_employer_amount
        if opts.young_relief and revenue > 0:
            exempt = max(0.0, min(revenue, p.young_relief_limit - ytd_exempt))
        else:
            exempt = 0.0
        ytd_exempt += exempt
        taxable_revenue = revenue - exempt
        taxable_share = taxable_revenue / revenue if revenue > 0 else 1.0

        social_taxable = employee_social * taxable_share
        kup_taxable = kup * taxable_share

        # 7. PIT base and advance. The month's base is split across the
        # cumulative 120 000 threshold - whatever part of it is still under
        # the running total is taxed at 12%, the rest at 32%.
        pit_base = whole(max(0.0, taxable_revenue - social_taxable - kup_taxable))
        under = max(0.0, min(pit_base, p.pit_threshold - ytd_pit_base))
        over = pit_base - under
        tax = p.pit_rate_1 * under + p.pit_rate_2 * over
        over_threshold = (ytd_pit_base + pit_base) > p.pit_threshold
        ytd_pit_base += pit_base

        monthly_reduction = p.pit_reduction_annual / 12
        reduction = monthly_reduction if (opts.pit2 and pit_base > 0) else 0.0
        pit_advance = max(0.0, whole(tax - reduction))

        # 8. Net pay.
        net = money(gross - employee_social - health - pit_advance - ppk_employee_amount)

        # 9. Employer side.
        employer_pension = money(p.employer_pension_rate * capped_base)
        employer_disability = money(p.employer_disability_rate * capped_base)
        employer_accident = money(opts.accident_rate * gross)
        employer_fp = money(p.employer_fp_rate * gross)
        employer_fgsp = money(p.employer_fgsp_rate * gross)
        employer_cost = money(
            gross
            + employer_pension
            + employer_disability
            + employer_accident
            + employer_fp
            + employer_fgsp
            + ppk_employer_amount
        )

        months.append(
            UopMonth(
                month=month,
                gross=gross,
                pension=pension,
                disability=disability,
                sickness=sickness,
                employee_social=employee_social,
                health=health,
                kup=kup,
                pit_base=pit_base,
                pit_advance=pit_advance,
                ppk_employee=ppk_employee_amount,
                ppk_employer=ppk_employer_amount,
                net=net,
                employer_pension=employer_pension,
                employer_disability=employer_disability,
                employer_accident=employer_accident,
                employer_fp=employer_fp,
                employer_fgsp=employer_fgsp,
                employer_cost=employer_cost,
                zus_capped=zus_capped,
                over_threshold=over_threshold,
            )
        )

    totals = sum_fields(months, skip=("month",))
    total_base = totals.get("pit_base", 0.0)
    annual_tax = (
        p.pit_rate_1 * min(total_base, p.pit_threshold)
        + p.pit_rate_2 * max(total_base - p.pit_threshold, 0.0)
        - p.pit_reduction_annual
    )
    annual_pit = whole(max(0.0, annual_tax))
    settlement = money(annual_pit - totals.get("pit_advance", 0.0))

    gross_total = totals.get("gross", 0.0)
    effective_rate = (
        None
        if gross_total == 0
        else (totals.get("employee_social", 0.0) + totals.get("health", 0.0) + annual_pit)
        / gross_total
    )
    pension_account_contributions = money(
        totals.get("pension", 0.0) + totals.get("employer_pension", 0.0)
    )

    return UopYear(
        params_year=p.year,
        months=months,
        totals=totals,
        annual_pit=annual_pit,
        settlement=settlement,
        effective_rate=effective_rate,
        pension_account_contributions=pension_account_contributions,
    )
