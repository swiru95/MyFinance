"""Polish tax/ZUS parameters, one immutable snapshot per tax year.

Rates and thresholds change every year (sometimes mid-year, but we only model
January rules) and each figure needs to be traceable to a source someone can
re-check. Keeping them in code rather than a database means a change is a
diffable, reviewable commit instead of a silent admin-panel edit, and the
values are covered by the same tests as the code that uses them.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def money(x: float) -> float:
    """Round to the nearest grosz, half up.

    Polish tax and ZUS law rounds 0.5 grosz up, not to even (banker's
    rounding, Python's `round()` default, would silently disagree with a
    hand-worked example on the exact halves that make good test cases).
    """
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def whole(x: float) -> float:
    """Round to the nearest whole PLN, half up - how PIT advances are paid."""
    return float(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def round_floats(obj):
    """Recursively money-round every float in a nested dict/list/tuple.

    Used by every result dataclass's `to_dict()` so the API boundary always
    sees 2 dp figures, regardless of how many intermediate additions of
    already-rounded grosze produced a value like 1234.5600000000002.
    """
    if isinstance(obj, float):
        return money(obj)
    if isinstance(obj, dict):
        return {k: round_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(round_floats(v) for v in obj)
    return obj


def sum_fields(items: list, skip: tuple[str, ...] = ()) -> dict:
    """Sum every numeric field (and every key of a dict-valued field) across
    a list of same-shaped dataclass instances - the `totals` row a schedule
    reports alongside its months. Non-numeric fields (a month number, a
    ryczałt tier index, a capped/over-threshold flag) are dropped rather than
    summed into a meaningless number.
    """
    if not items:
        return {}
    totals: dict = {}
    for f in dataclasses.fields(items[0]):
        if f.name in skip:
            continue
        values = [getattr(it, f.name) for it in items]
        first = values[0]
        if isinstance(first, dict):
            totals[f.name] = {k: money(sum(v[k] for v in values)) for k in first}
        elif isinstance(first, bool):
            continue
        elif isinstance(first, (int, float)):
            totals[f.name] = money(sum(values))
    return totals


@dataclass(frozen=True)
class TaxYear:
    year: int
    minimum_wage: float
    avg_wage_forecast: float
    avg_wage_q4_prev: float
    zus_annual_cap: float
    jdg_full_base: float
    jdg_preferential_base: float
    health_min_base_share: float
    linear_health_deduction_limit: float
    ryczalt_health_tiers: tuple[float, float, float]  # monthly amounts, tier 1/2/3
    vat_exempt_limit: float
    ike_limit: float
    ikze_limit: float
    ikze_limit_jdg: float
    verified_on: date
    sources: tuple[tuple[str, str], ...]  # (what, url)

    ryczalt_tier_thresholds: tuple[float, float] = (60_000, 300_000)
    young_relief_limit: float = 85_528
    pit_threshold: float = 120_000
    pit_rate_1: float = 0.12
    pit_rate_2: float = 0.32
    pit_reduction_annual: float = 3_600
    linear_rate: float = 0.19
    capital_gains_rate: float = 0.19
    vat_standard: float = 0.23
    kup_monthly: float = 250
    kup_monthly_commuting: float = 300
    kup_creative_rate: float = 0.5
    kup_creative_annual_limit: float = 120_000

    # Employee ZUS (umowa o pracę side).
    employee_pension_rate: float = 0.0976
    employee_disability_rate: float = 0.015
    employee_sickness_rate: float = 0.0245
    employee_health_rate: float = 0.09

    # Employer ZUS. Accident rate is not here: it varies by business/risk
    # class, so it lives on UopOptions instead of the shared yearly params.
    employer_pension_rate: float = 0.0976
    employer_disability_rate: float = 0.065
    employer_fp_rate: float = 0.0245
    employer_fgsp_rate: float = 0.0010

    # JDG (self-employed) ZUS.
    jdg_pension_rate: float = 0.1952
    jdg_disability_rate: float = 0.08
    jdg_accident_rate: float = 0.0167
    jdg_sickness_rate: float = 0.0245
    jdg_fp_rate: float = 0.0245

    # JDG health contribution, as a share of income (skala/liniowy only -
    # ryczałt uses the flat monthly tiers above instead).
    jdg_health_skala_rate: float = 0.09
    jdg_health_liniowy_rate: float = 0.049

    @property
    def health_min_monthly(self) -> float:
        """Floor under skala/liniowy JDG health, even at zero or negative
        income: health insurance is compulsory, not income-tested."""
        return money(0.09 * self.minimum_wage * self.health_min_base_share)

    @property
    def voluntary_nfz_monthly(self) -> float:
        """What someone with no other insured status pays to stay covered."""
        return money(0.09 * self.avg_wage_q4_prev)


PARAMS: dict[int, TaxYear] = {
    2025: TaxYear(
        year=2025,
        minimum_wage=4_666.00,
        avg_wage_forecast=8_673.00,
        avg_wage_q4_prev=8_549.18,
        zus_annual_cap=260_190,
        jdg_full_base=5_203.80,
        jdg_preferential_base=1_399.80,
        health_min_base_share=0.75,
        linear_health_deduction_limit=12_900,
        ryczalt_health_tiers=(461.66, 769.43, 1_384.97),
        vat_exempt_limit=200_000,
        ike_limit=26_019.00,
        ikze_limit=10_407.60,  # 1.2 x 8 673
        ikze_limit_jdg=15_611.40,  # 1.8 x 8 673
        verified_on=date(2026, 9, 27),
        sources=(
            ("ZUS składki i wskaźniki", "https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki/wskazniki"),
            ("Roczne ograniczenie podstawy wymiaru składek", "https://poradnikprzedsiebiorcy.pl/-roczne-ograniczenie-podstawy-wymiaru-skladek-na-ubezpieczenia-emerytalne-i-rentowe"),
            ("Limity IKE/IKZE", "https://www.analizy.pl/oszczedzanie-na-emeryture/24551/limity-wplat-na-ike-ikze-i-ppe"),
            ("Limit zwolnienia podmiotowego VAT", "https://poradnikprzedsiebiorcy.pl/-limit-zwolnienia-podmiotowego-w-vat"),
            ("Kwota wolna od podatku", "https://www.pit.pl/kwota-wolna-od-podatku/"),
        ),
    ),
    2026: TaxYear(
        year=2026,
        minimum_wage=4_806.00,
        avg_wage_forecast=9_420.00,
        avg_wage_q4_prev=9_228.64,
        zus_annual_cap=282_600,
        jdg_full_base=5_652.00,
        jdg_preferential_base=1_441.80,
        health_min_base_share=1.00,
        linear_health_deduction_limit=14_100,
        ryczalt_health_tiers=(498.35, 830.58, 1_495.04),
        vat_exempt_limit=240_000,
        ike_limit=28_260.00,
        ikze_limit=11_304.00,
        ikze_limit_jdg=16_956.00,
        verified_on=date(2026, 9, 27),
        sources=(
            ("ZUS składki i wskaźniki", "https://www.zus.pl/baza-wiedzy/skladki-wskazniki-odsetki/wskazniki"),
            ("Składka zdrowotna 2026", "https://www.infakt.pl/blog/skladka-zdrowotna-2026-skala-podatkowa-podatek-liniowy-ryczalt-i-inne-formy/"),
            ("Roczne ograniczenie podstawy wymiaru składek", "https://poradnikprzedsiebiorcy.pl/-roczne-ograniczenie-podstawy-wymiaru-skladek-na-ubezpieczenia-emerytalne-i-rentowe"),
            ("Limity IKE/IKZE", "https://www.analizy.pl/oszczedzanie-na-emeryture/24551/limity-wplat-na-ike-ikze-i-ppe"),
            ("Limit zwolnienia podmiotowego VAT", "https://poradnikprzedsiebiorcy.pl/-limit-zwolnienia-podmiotowego-w-vat"),
            ("Kwota wolna od podatku", "https://www.pit.pl/kwota-wolna-od-podatku/"),
        ),
    ),
}


# Years before this have no rules loaded. Callers that walk history (the
# monthly page, income schedules) skip them rather than guess: 2024 had two
# minimum wages and different bases, and a plausible-looking wrong net is
# worse than an honest gap.
EARLIEST_YEAR = min(PARAMS)


def get_params(year: int) -> TaxYear:
    """Rules for `year`, or the newest known year for anything later.

    Tax law is only ever legislated up to the current year, so a forecast
    for next year has nothing better to reuse than "this year's rules until
    told otherwise" - the caller is expected to surface `params_year` from
    the result so a stale assumption is visible, not silent.
    """
    if year in PARAMS:
        return PARAMS[year]
    earliest = min(PARAMS)
    if year < earliest:
        raise ValueError(f"no Polish tax parameters known before {earliest}")
    latest = max(y for y in PARAMS if y <= year)
    return PARAMS[latest]
