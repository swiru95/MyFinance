"""JDG (jednoosobowa działalność gospodarcza / sole proprietorship) maths.

Skala and liniowy tax income the same way (revenue minus costs minus social
contributions) and differ only in the rate and the health-contribution base;
ryczałt is a different animal entirely - a flat percentage of revenue, with
health set by a tier rather than computed from income. Keeping all three in
one schedule function means the comparator (compare.py) can treat a
`B2bYear` uniformly regardless of which form produced it.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from .params import TaxYear, get_params, money, round_floats, sum_fields, whole

DUE_DAYS = {"zus": 20, "pit": 20, "vat": 25}  # day of the following month

ALLOWED_RYCZALT_RATES = {0.02, 0.03, 0.055, 0.085, 0.10, 0.12, 0.14, 0.15, 0.17}

_EMPTY_SOCIAL = {
    "base": 0.0,
    "pension": 0.0,
    "disability": 0.0,
    "accident": 0.0,
    "sickness": 0.0,
    "fp": 0.0,
    "total": 0.0,
}


@dataclass(frozen=True)
class B2bOptions:
    tax_form: str = "liniowy"  # skala | liniowy | ryczalt
    ryczalt_rate: float = 0.12
    zus_stage: str = "full"  # start | preferential | maly_zus_plus | full
    custom_base: float | None = None  # required for maly_zus_plus
    sickness: bool = False  # voluntary chorobowe
    vat: str = "standard"  # standard | exempt | reverse_charge
    vat_rate: float = 0.23
    costs_vat_rate: float = 0.23


def jdg_social_monthly(
    p: TaxYear, stage: str, sickness: bool, custom_base: float | None = None
) -> dict:
    """One month's JDG social contributions for a given ZUS stage.

    Returns money-rounded grosze, not a rate applied later - ZUS bills each
    component separately and rounds each one, so summing pre-rounded parts
    is what "total" actually means on a real payment.
    """
    if stage == "start":
        # Ulga na start: no social contributions at all (health is handled
        # separately by the caller - it is never optional).
        return dict(_EMPTY_SOCIAL)
    if stage == "preferential":
        base = p.jdg_preferential_base
        pays_fp = False
    elif stage == "maly_zus_plus":
        if custom_base is None:
            raise ValueError("custom_base is required for zus_stage='maly_zus_plus'")
        if not (p.jdg_preferential_base <= custom_base <= p.jdg_full_base):
            raise ValueError(
                "custom_base for Mały ZUS Plus must be between the preferential "
                "and full ZUS bases"
            )
        base = custom_base
        pays_fp = False
    elif stage == "full":
        base = p.jdg_full_base
        pays_fp = True
    else:
        raise ValueError(f"unknown zus_stage {stage!r}")

    pension = money(p.jdg_pension_rate * base)
    disability = money(p.jdg_disability_rate * base)
    accident = money(p.jdg_accident_rate * base)
    sickness_amt = money(p.jdg_sickness_rate * base) if sickness else 0.0
    fp = money(p.jdg_fp_rate * base) if pays_fp else 0.0
    total = money(pension + disability + accident + sickness_amt + fp)

    return {
        "base": base,
        "pension": pension,
        "disability": disability,
        "accident": accident,
        "sickness": sickness_amt,
        "fp": fp,
        "total": total,
    }


def _pick_ryczalt_tier(p: TaxYear, full_year_base: float) -> tuple[int, float]:
    """Which of the three flat health tiers applies for the whole year.

    The tier is decided by the full year's revenue-minus-social figure, not
    a YTD running total: legally it is set from last year's result, but for
    planning what matters is the actual annual cost, so we use the year
    being planned itself and apply it uniformly across all 12 months.
    """
    low, high = p.ryczalt_tier_thresholds
    if full_year_base <= low:
        return 1, p.ryczalt_health_tiers[0]
    if full_year_base <= high:
        return 2, p.ryczalt_health_tiers[1]
    return 3, p.ryczalt_health_tiers[2]


@dataclass
class B2bMonth:
    month: int
    revenue: float
    costs: float
    invoice_gross: float
    vat_output: float
    vat_input: float
    vat_due: float
    social: dict
    social_total: float
    income: float
    health: float
    pit_advance: float
    take_home: float
    set_aside: float
    health_tier: int | None

    def to_dict(self) -> dict:
        return round_floats(dataclasses.asdict(self))


@dataclass
class B2bYear:
    params_year: int
    tax_form: str
    months: list[B2bMonth]
    totals: dict
    effective_rate: float | None
    pension_account_contributions: float
    warnings: list[str]

    def to_dict(self) -> dict:
        return round_floats(dataclasses.asdict(self))


def b2b_schedule(
    year: int,
    revenue_by_month: list[float],
    costs_by_month: list[float],
    opts: B2bOptions,
    active_by_month: list[bool] | None = None,
) -> B2bYear:
    p = get_params(year)
    if len(revenue_by_month) != 12 or len(costs_by_month) != 12:
        raise ValueError("revenue_by_month and costs_by_month must have 12 entries")

    if active_by_month is None:
        active_by_month = [
            revenue_by_month[i] > 0 or costs_by_month[i] > 0 for i in range(12)
        ]

    is_vat_payer = opts.vat in ("standard", "reverse_charge")

    social_by_month = [
        jdg_social_monthly(p, opts.zus_stage, opts.sickness, opts.custom_base)
        if active_by_month[i]
        else dict(_EMPTY_SOCIAL)
        for i in range(12)
    ]

    ryczalt_tier = ryczalt_health = None
    if opts.tax_form == "ryczalt":
        full_year_base = sum(revenue_by_month) - sum(
            s["total"] for s in social_by_month
        )
        ryczalt_tier, ryczalt_health = _pick_ryczalt_tier(p, full_year_base)

    months: list[B2bMonth] = []
    ytd_income = 0.0  # skala/liniowy taxable income
    ytd_health = 0.0  # for liniowy's health-deduction limit
    prev_advances = 0.0  # skala/liniowy: cumulative advances already paid

    for i in range(12):
        month = i + 1
        revenue = revenue_by_month[i]
        costs = costs_by_month[i]
        active = active_by_month[i]
        social = social_by_month[i]
        social_total = social["total"]

        # Input VAT on a cost is only recoverable for a VAT payer; an exempt
        # business simply pays the gross cost, which is what actually leaves
        # its account and what should reduce both income and take-home.
        deductible_costs = (
            costs if is_vat_payer else money(costs * (1 + opts.costs_vat_rate))
        )

        # Ryczałt taxes revenue, not income - this "income" is informational
        # (shown for comparability) and never feeds its own PIT advance.
        social_for_income = social_total if opts.tax_form in ("skala", "liniowy") else 0.0
        income = money(revenue - deductible_costs - social_for_income)
        ytd_income += income

        if not active:
            health = 0.0
            health_tier = None
        elif opts.tax_form == "skala":
            health = max(
                money(p.jdg_health_skala_rate * max(income, 0.0)), p.health_min_monthly
            )
            health_tier = None
        elif opts.tax_form == "liniowy":
            health = max(
                money(p.jdg_health_liniowy_rate * max(income, 0.0)), p.health_min_monthly
            )
            health_tier = None
        else:  # ryczalt
            health = ryczalt_health
            health_tier = ryczalt_tier
        ytd_health += health

        if opts.tax_form == "skala":
            ytd_tax = max(
                0.0,
                p.pit_rate_1 * min(ytd_income, p.pit_threshold)
                + p.pit_rate_2 * max(ytd_income - p.pit_threshold, 0.0)
                - p.pit_reduction_annual,
            )
            pit_advance = max(0.0, whole(ytd_tax) - prev_advances)
        elif opts.tax_form == "liniowy":
            ytd_base = ytd_income - min(ytd_health, p.linear_health_deduction_limit)
            ytd_tax = p.linear_rate * max(ytd_base, 0.0)
            pit_advance = max(0.0, whole(ytd_tax) - prev_advances)
        else:  # ryczalt - each month settles on its own, never cumulative
            base = whole(max(0.0, revenue - social_total - 0.5 * health))
            pit_advance = whole(opts.ryczalt_rate * base)
        prev_advances += pit_advance

        output = money(revenue * opts.vat_rate) if opts.vat == "standard" else 0.0
        input_vat = money(costs * opts.costs_vat_rate) if is_vat_payer else 0.0
        vat_due = money(output - input_vat)
        invoice_gross = money(revenue + output)

        take_home = money(revenue - deductible_costs - social_total - health - pit_advance)
        set_aside = money(social_total + health + pit_advance + max(vat_due, 0.0))

        months.append(
            B2bMonth(
                month=month,
                revenue=revenue,
                costs=costs,
                invoice_gross=invoice_gross,
                vat_output=output,
                vat_input=input_vat,
                vat_due=vat_due,
                social=social,
                social_total=social_total,
                income=income,
                health=health,
                pit_advance=pit_advance,
                take_home=take_home,
                set_aside=set_aside,
                health_tier=health_tier,
            )
        )

    totals = sum_fields(months, skip=("month", "health_tier"))
    revenue_total = totals.get("revenue", 0.0)
    effective_rate = (
        None
        if revenue_total == 0
        else (
            totals.get("social_total", 0.0)
            + totals.get("health", 0.0)
            + totals.get("pit_advance", 0.0)
        )
        / revenue_total
    )
    pension_account_contributions = money(totals.get("social", {}).get("pension", 0.0))

    warnings: list[str] = []
    if opts.vat == "exempt" and sum(revenue_by_month) > p.vat_exempt_limit:
        warnings.append("vat_exempt_limit_exceeded")
    if opts.tax_form == "ryczalt" and not any(
        abs(opts.ryczalt_rate - r) < 1e-9 for r in ALLOWED_RYCZALT_RATES
    ):
        warnings.append("ryczalt_rate_unusual")

    return B2bYear(
        params_year=p.year,
        tax_form=opts.tax_form,
        months=months,
        totals=totals,
        effective_rate=effective_rate,
        pension_account_contributions=pension_account_contributions,
        warnings=warnings,
    )
