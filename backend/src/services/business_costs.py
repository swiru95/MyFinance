"""Fixed JDG costs: the ZUS social and health contributions a B2B income
source owes every month, whether or not it billed anything.

A B2B source's income is already reported *net* of these (see
services/income.py's source_year: `net_pln = breakdown["take_home"]`), so
folding them into the recurring-expense side of the budget would subtract
them twice. They still need to show up somewhere, though - closing the JDG
does not close these bills - so routes/expenses.py keeps them as a distinct
figure alongside (not inside) the typed expense total.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models.income import IncomeEntry, IncomeSource
from ..services.income import is_active_in_month, source_year
from ..services.price_service import PriceService
from ..tax.pl.b2b import jdg_social_monthly
from ..tax.pl.params import TaxYear, get_params, money


def _convert(ps: PriceService, amount: float, currency: str, to: str) -> float:
    """`amount` in `currency` converted to `to`.

    Imported lazily: routes/__init__ pulls in routes.monthly, whose schemas
    import services.budget, so a top-level import of routes.helpers here
    would be circular whenever this module is imported before that chain
    finishes (see services/budget.py's convert_currency import for the same
    issue).
    """
    from ..routes.helpers import convert_currency

    return convert_currency(ps, amount, currency, to)


def _health_fixed_pln(
    db: Session, src: IncomeSource, year: int, p: TaxYear
) -> float:
    """What this source's health contribution costs even at zero revenue.

    skala/liniowy: the statutory minimum, income-tested maths never applies
    below it. ryczałt: the tier actually paid - the source's own choice if it
    pinned one, else the tier its full-year revenue implies (the same figure
    source_year/b2b_schedule already compute, reused rather than
    re-derived).
    """
    tax_form = src.params.get("tax_form", "liniowy")
    if tax_form != "ryczalt":
        return p.health_min_monthly

    tier = src.params.get("ryczalt_health_tier")
    if tier is None:
        entries = db.query(IncomeEntry).filter(IncomeEntry.source_id == src.id).all()
        # PLN throughout - only the tier read off the result matters here,
        # not its money figures, so the base currency choice is irrelevant.
        sy = source_year(src, entries, year, PriceService("PLN"), "PLN")
        tier = sy.get("ryczalt_health_tier_actual") or 1
    return p.ryczalt_health_tiers[tier - 1]


def fixed_contributions(
    db: Session, month: str, ps: PriceService, base: str
) -> list[dict]:
    """ZUS social + health contributions owed by every B2B source active in
    `month`, converted to `base`.

    This is the fixed cost of keeping the JDG open - independent of that
    month's revenue, and owed even in a month with none.
    """
    year = int(month[:4])
    p = get_params(year)

    out: list[dict] = []
    sources = db.query(IncomeSource).filter(IncomeSource.kind == "b2b").all()
    for src in sources:
        if not is_active_in_month(src, month):
            continue
        params = src.params or {}
        social = jdg_social_monthly(
            p,
            params.get("zus_stage", "full"),
            bool(params.get("sickness", False)),
            params.get("custom_base"),
        )
        health_pln = _health_fixed_pln(db, src, year, p)

        social_base = _convert(ps, social["total"], "PLN", base)
        health_base = _convert(ps, health_pln, "PLN", base)
        out.append(
            {
                "source_id": src.id,
                "name": src.name,
                "social": money(social_base),
                "health_fixed": money(health_base),
                "total": money(social_base + health_base),
                "currency": base,
            }
        )
    return out
