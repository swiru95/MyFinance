"""Polish tax preview API: forward schedules, comparison, and gross-from-net
reverse solving, all through the engine in tax/pl/. Nothing here computes tax
itself - it only validates input and shapes the engine's dataclasses into
JSON.

These are estimates for education and planning, not tax advice, so every
response carries `disclaimer_key` for the frontend to render.
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, HTTPException

from ..schemas.tax import (
    B2bPreviewIn,
    ComparePreviewIn,
    ReverseIn,
    UopPreviewIn,
)
from ..tax.pl.b2b import b2b_schedule, jdg_social_monthly
from ..tax.pl.compare import compare_uop_b2b
from ..tax.pl.params import get_params
from ..tax.pl.reverse import reverse_b2b, reverse_uop
from ..tax.pl.uop import uop_schedule

router = APIRouter(prefix="/api/tax", tags=["tax"])

_DISCLAIMER = {"disclaimer_key": "tax.disclaimer"}


@router.get("/params/{year}")
def tax_params(year: int) -> dict:
    """Every rate and threshold for `year`, for the education view."""
    try:
        p = get_params(year)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    jdg_social = {
        stage: {
            "with_sickness": jdg_social_monthly(p, stage, sickness=True),
            "without_sickness": jdg_social_monthly(p, stage, sickness=False),
        }
        for stage in ("start", "preferential", "full")
    }
    return {
        **dataclasses.asdict(p),
        "params_year": p.year,
        "health_min_monthly": p.health_min_monthly,
        "voluntary_nfz_monthly": p.voluntary_nfz_monthly,
        "jdg_social": jdg_social,
        **_DISCLAIMER,
    }


@router.post("/uop")
def preview_uop(payload: UopPreviewIn) -> dict:
    result = uop_schedule(payload.year, payload.gross_list(), payload.options.to_options())
    return {**result.to_dict(), **_DISCLAIMER}


@router.post("/b2b")
def preview_b2b(payload: B2bPreviewIn) -> dict:
    result = b2b_schedule(
        payload.year, payload.revenue_list(), payload.costs_list(), payload.options.to_options()
    )
    return {**result.to_dict(), **_DISCLAIMER}


@router.post("/compare")
def preview_compare(payload: ComparePreviewIn) -> dict:
    result = compare_uop_b2b(
        payload.year,
        payload.uop_gross_monthly,
        payload.uop_options.to_options(),
        payload.b2b_revenue_monthly,
        payload.b2b_costs_monthly,
        payload.b2b_options.to_options(),
        paid_leave_days=payload.paid_leave_days,
        working_days=payload.working_days,
        b2b_billed_per_day=payload.b2b_billed_per_day,
    )
    return {**result, **_DISCLAIMER}


@router.post("/reverse")
def preview_reverse(payload: ReverseIn) -> dict:
    """Gross/revenue needed to hit `target_net_monthly`, for umowa o pracę
    and for every b2b tax form (the b2b options with `tax_form` swapped)."""
    uop_result = reverse_uop(payload.year, payload.target_net_monthly, payload.uop_options.to_options())

    b2b_base_opts = payload.b2b_options.to_options()
    b2b_result = {
        form: reverse_b2b(
            payload.year,
            payload.target_net_monthly,
            payload.costs_monthly,
            dataclasses.replace(b2b_base_opts, tax_form=form),
        )
        for form in ("skala", "liniowy", "ryczalt")
    }
    return {"uop": uop_result, "b2b": b2b_result, **_DISCLAIMER}
