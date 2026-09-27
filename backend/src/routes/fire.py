"""FIRE settings + the assembled /api/fire projection.

This is the wiring layer: every number here is read from the portfolio,
expenses and income modules, and the actual math lives in services/fire.py
and services/returns.py (real terms in, real terms out - see their
docstrings). Nothing here recomputes anything those modules already do.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.position import Position
from ..models.settings import Setting
from ..profiles import for_category
from ..schemas.fire import FireSettings
from ..services import fire
from ..services.returns import blended_nominal_return, real_rate
from ..tax.pl.b2b import B2bOptions
from ..tax.pl.params import get_params
from ..tax.pl.reverse import reverse_b2b, reverse_uop
from ..tax.pl.uop import UopOptions
from . import monthly as monthly_routes
from . import statistics as statistics_routes
from .expenses import expense_summary
from .helpers import today_in

router = APIRouter(prefix="/api/fire", tags=["fire"])

_SETTINGS_KEY = "fire"


def _load_settings(db: Session) -> FireSettings:
    row = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
    if not row or not row.value:
        return FireSettings()
    return FireSettings.model_validate(json.loads(row.value))


def _save_settings(db: Session, settings: FireSettings) -> None:
    row = db.query(Setting).filter(Setting.key == _SETTINGS_KEY).first()
    payload = settings.model_dump_json()
    if row is None:
        db.add(Setting(key=_SETTINGS_KEY, value=payload))
    else:
        row.value = payload
    db.commit()


def _income_source_options(db: Session, month: str) -> tuple[UopOptions, B2bOptions, float]:
    """UoP/B2B options (and B2B monthly costs) from the user's own sources.

    "What would I have to earn" is only useful on the user's own terms - their
    PPK choice, creative-work share, ZUS stage and business costs - so the
    first source of each kind active this month supplies them. Without one,
    the engine's defaults stand (B2B: full ZUS, no sickness, standard VAT,
    no costs).
    """
    from ..models.income import IncomeSource
    from ..schemas.income import B2bIncomeParams, UopIncomeParams
    from ..services.income import is_active_in_month

    uop_opts, b2b_opts, b2b_costs = UopOptions(), B2bOptions(), 0.0
    sources = db.query(IncomeSource).order_by(IncomeSource.id).all()
    active = [s for s in sources if is_active_in_month(s, month)]
    uop = next((s for s in active if s.kind == "uop"), None)
    b2b = next((s for s in active if s.kind == "b2b"), None)
    if uop is not None:
        uop_opts = UopIncomeParams.model_validate(uop.params or {}).to_options()
    if b2b is not None:
        params = B2bIncomeParams.model_validate(b2b.params or {})
        b2b_opts = params.to_options()
        b2b_costs = float(params.costs_monthly or 0.0)
    return uop_opts, b2b_opts, b2b_costs


@router.get("/settings", response_model=FireSettings)
def get_fire_settings(db: Session = Depends(get_db)):
    return _load_settings(db)


@router.put("/settings", response_model=FireSettings)
def update_fire_settings(payload: FireSettings, db: Session = Depends(get_db)):
    _save_settings(db, payload)
    return payload


@router.get("")
def get_fire(db: Session = Depends(get_db)):
    """Assemble one person's FIRE picture from the rest of the app and
    hand it to services/fire.compute() - see wp-e-flows-fire-api.md for the
    field-by-field rationale.
    """
    settings = _load_settings(db)
    today = today_in(db)

    if settings.birth_year is None:
        return {"needs": ["birth_year"], "settings": settings, "result": None}

    current_age = today.year - settings.birth_year

    alloc = statistics_routes.allocation(db=db)
    expenses_summary = expense_summary(db=db)
    committed = expenses_summary.monthly_total
    months = monthly_routes.analytics(months_back=11, months_ahead=0, db=db)

    # Illiquid holdings (a watch, a vehicle) cannot fund withdrawals, so they
    # are dropped from every FIRE figure below and only reported as an
    # excluded total. Everything that stays is split by wrapper: a
    # tax-advantaged account still counts toward the FI number, but not
    # toward what a bridge to that number can spend before its access age.
    excluded_illiquid = 0.0
    liquid_items: list[dict] = []
    for item in alloc["items"]:
        band = item["profile"] or for_category(item["category"])
        if band == "illiquid":
            excluded_illiquid += item["value"]
        else:
            liquid_items.append(item)

    # Wrapper alone does not mean locked: OKI is tax-advantaged but carries no
    # age lock (see tax/pl/wrappers.py), so "wrapped" here means specifically
    # a wrapper with an access age, not just any non-empty wrapper string.
    wrapped = sum(
        item["value"] for item in liquid_items if item.get("wrapper") in fire.ACCESS_AGE
    )
    accessible_raw = sum(
        item["value"] for item in liquid_items if item.get("wrapper") not in fire.ACCESS_AGE
    )
    reserve = settings.emergency_months * committed
    accessible = max(accessible_raw - reserve, 0.0)
    fi_assets = accessible + wrapped

    if settings.monthly_spend_override is not None:
        monthly_spend = settings.monthly_spend_override
        spend_source = "override"
    elif months.months_with_spend >= 3 and (months.avg_actual or 0) > 0:
        monthly_spend = months.avg_actual
        spend_source = "recorded"
    else:
        # Personal only, not the full committed (incl. JDG ZUS/health): once
        # FI is reached the JDG is assumed closed, so its fixed contributions
        # stop - and include_health_cost/health_cost_monthly below already
        # add back voluntary NFZ health for the post-JDG years.
        monthly_spend = expenses_summary.monthly_total_personal
        spend_source = "committed"

    monthly_net_income = months.avg_income or 0.0

    blended_nominal = blended_nominal_return(liquid_items)
    real_return = (
        settings.real_return_override
        if settings.real_return_override is not None
        else real_rate(blended_nominal, settings.inflation)
    )

    # Contribution is read off actual money movement when enough of it is
    # known (flows), rather than assumed - see flow_in_base on Position.
    # Each asset's very first snapshot is an opening balance, not a flow, so
    # it is excluded the same way create_position never derives one for it.
    window_start = today - timedelta(days=365)
    all_positions = (
        db.query(Position)
        .order_by(Position.asset_id, Position.timestamp.asc(), Position.id.asc())
        .all()
    )
    first_id_by_asset: dict[int, int] = {}
    for p in all_positions:
        first_id_by_asset.setdefault(p.asset_id, p.id)
    in_window = [p for p in all_positions if p.timestamp.date() >= window_start]
    recent = [p for p in in_window if p.id != first_id_by_asset.get(p.asset_id)]
    flow_coverage = (
        sum(1 for p in recent if p.flow_in_base is not None) / len(recent)
        if recent
        else 0.0
    )
    if recent and flow_coverage >= 0.8:
        # An opening balance is not a flow, so first snapshots stay out of
        # the coverage count - but one entered *with* a flow (a new holding
        # bought from income) is saving and belongs in the sum.
        total_flow = sum(float(p.flow_in_base) for p in in_window if p.flow_in_base is not None)
        # Averaged over the months the history actually spans: dividing a
        # three-month history by twelve would report a quarter of the saving.
        earliest = min(p.timestamp.date() for p in in_window)
        months_span = min(max((today - earliest).days / 30.44, 1.0), 12.0)
        monthly_contribution = total_flow / months_span
        contribution_source = "flows"
    elif surpluses := [p.surplus for p in months.timeline if p.surplus is not None]:
        # Income minus typed spend, over the same months on both sides.
        monthly_contribution = sum(surpluses) / len(surpluses)
        contribution_source = "recorded"
    else:
        monthly_contribution = 0.0
        contribution_source = "none"

    params = get_params(today.year)
    health_cost_monthly = params.voluntary_nfz_monthly if settings.include_health_cost else 0.0

    assumptions = fire.FireAssumptions(
        current_age=current_age,
        retirement_age=settings.retirement_age,
        target_fi_age=settings.target_fi_age,
        swr=settings.swr,
        real_return=real_return,
        monthly_spend=monthly_spend,
        monthly_net_income=monthly_net_income,
        monthly_contribution=monthly_contribution,
        fi_assets=fi_assets,
        accessible_assets=accessible,
        zus_pension_monthly=settings.zus_pension_monthly,
        barista_income_monthly=settings.barista_income_monthly,
        health_cost_monthly=health_cost_monthly,
        gain_share=settings.gain_share,
        lean_factor=settings.lean_factor,
        fat_factor=settings.fat_factor,
    )
    result = fire.compute(assumptions)

    required_income = None
    if result["required"] is not None:
        target_net_monthly = result["required"]["required_net_income"]
        uop_opts, b2b_defaults, b2b_costs = _income_source_options(
            db, f"{today.year:04d}-{today.month:02d}"
        )
        required_income = {
            "uop": reverse_uop(today.year, target_net_monthly, uop_opts),
            "b2b_skala": reverse_b2b(
                today.year, target_net_monthly, b2b_costs,
                dataclasses.replace(b2b_defaults, tax_form="skala"),
            ),
            "b2b_liniowy": reverse_b2b(
                today.year, target_net_monthly, b2b_costs,
                dataclasses.replace(b2b_defaults, tax_form="liniowy"),
            ),
            "b2b_ryczalt": reverse_b2b(
                today.year, target_net_monthly, b2b_costs,
                dataclasses.replace(b2b_defaults, tax_form="ryczalt"),
            ),
        }

    inputs = {
        "current_age": current_age,
        "retirement_age": settings.retirement_age,
        "target_fi_age": settings.target_fi_age,
        "swr": settings.swr,
        "real_return": round(real_return, 4),
        "monthly_spend": round(monthly_spend, 2),
        "monthly_net_income": round(monthly_net_income, 2),
        "monthly_contribution": round(monthly_contribution, 2),
        "fi_assets": round(fi_assets, 2),
        "accessible_assets": round(accessible, 2),
        "wrapped_assets": round(wrapped, 2),
        "zus_pension_monthly": settings.zus_pension_monthly,
        "barista_income_monthly": settings.barista_income_monthly,
        "health_cost_monthly": round(health_cost_monthly, 2),
        "gain_share": settings.gain_share,
        "lean_factor": settings.lean_factor,
        "fat_factor": settings.fat_factor,
        "spend_source": spend_source,
        "contribution_source": contribution_source,
        "flow_coverage": round(flow_coverage, 4),
        "reserve": round(reserve, 2),
        "excluded_illiquid": round(excluded_illiquid, 2),
        "blended_nominal": round(blended_nominal, 4),
        "inflation": settings.inflation,
        "params_year": params.year,
    }

    return {
        "settings": settings,
        "inputs": inputs,
        "result": result,
        "required_income": required_income,
        "disclaimer_key": "fire.disclaimer",
    }
