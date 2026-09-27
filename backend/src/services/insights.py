"""Insight jobs: profile analysis, monthly digest, next-best-step ranking.

Same shape as services/assessment.py - deterministic snapshot in, model text
out - except profile and next_steps ask for structured JSON (llm.complete's
`response_format`) instead of free Markdown, because their output feeds
pills/cards/ranked lists rather than just rendering. Every generated number
is checked against its own snapshot afterwards (services/grounding.py)
before the row is marked done; nothing here ever computes a figure itself.
"""
from __future__ import annotations

import copy
import json
import statistics

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..models.settings import Setting
from ..schemas.insight import NextStepsResult, ProfileAnswers, ProfileResult
from . import assessment, grounding, ladder, llm

_PROFILE_ANSWERS_KEY = "profile_answers"

PROFILE_JSON_SCHEMA = {
    "name": "profile_analysis",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stated_tolerance": {"type": "string", "enum": ["low", "medium", "high"]},
            "capacity": {"type": "string", "enum": ["low", "medium", "high"]},
            "revealed": {"type": "string", "enum": ["low", "medium", "high"]},
            "mismatches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "about": {"type": "string"},
                        "stated": {"type": "string"},
                        "actual": {"type": "string"},
                        "why_it_matters": {"type": "string"},
                    },
                    "required": ["about", "stated", "actual", "why_it_matters"],
                },
            },
            "priorities": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
            "suggested_style": {
                "type": "string", "enum": ["safe", "balanced", "risky", "long_term"],
            },
            "summary_md": {"type": "string"},
        },
        "required": [
            "stated_tolerance", "capacity", "revealed", "mismatches",
            "priorities", "suggested_style", "summary_md",
        ],
    },
}

NEXT_STEPS_JSON_SCHEMA = {
    "name": "next_steps_ranking",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "steps": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "key": {"type": "string"},
                        "title": {"type": "string"},
                        "why_md": {"type": "string"},
                    },
                    "required": ["key", "title", "why_md"],
                },
            },
        },
        "required": ["steps"],
    },
}

_PROFILE_SYSTEM = """You are a careful personal-finance analyst profiling one \
person's attitude to risk against what their own numbers show.

You are given their questionnaire answers, the deterministic shape of their \
income and safety net, and how their portfolio is actually allocated by \
risk band.

Answer only with one JSON object matching the schema you were given. Do not \
add commentary before or after it.

Rules you must follow:
- Use only the figures given below. Never invent a number, a holding, or an \
answer they did not give.
- "capacity" is what their situation can absorb - income stability, \
runway, how close they are to financial independence, dependents - judge it \
from the inputs given, not from their stated tolerance.
- "revealed" is what their current allocation actually says about their \
risk appetite, independent of what they say they want.
- List a mismatch only where stated, capacity and revealed genuinely \
disagree - do not manufacture one to fill the list.
- priorities is at most 3 short phrases, ranked by importance.
- summary_md is two or three plain sentences of Markdown, no heading.
- This is analysis of their own figures, not regulated financial advice."""

_NEXT_STEPS_SYSTEM = """You are ranking a short list of candidate next \
actions for one person's finances by how much each would matter, for this \
specific person.

You are given each candidate as a key with its status and the figures \
behind it, and - when available - the profile this person was already \
assessed against. Only the keys listed are real candidates; there is no \
other one to choose from.

Answer only with one JSON object matching the schema you were given: at \
most 3 steps, ordered by impact, each with the exact candidate key, a short \
title, and 2-3 sentences explaining why it matters for this person \
specifically.

Rules you must follow:
- key must be copied exactly from the candidates given - never invent one, \
never rank one that is not listed.
- Use only the figures given. Never invent a number.
- Do not recommend specific tickers, funds or products.
- This is analysis of their own figures, not regulated financial advice."""

_DIGEST_SYSTEM = """You are writing a short monthly digest of one person's \
finances from their own recorded figures for one month, read against their \
trailing 12-month average.

Write the digest in English as Markdown, using exactly these sections:

## This month
Three sentences: income, spend, and the single most important thing about \
this month.

## What changed
What moved compared to the trailing average - income, spend, portfolio \
value - each tied to a figure.

## One thing to focus on
Exactly one action. Tie it to one ladder status key or one flagged item \
given below, and say what to actually do about it.

Rules you must follow:
- Use only the figures given below. Never invent a number.
- Quote amounts in {currency}, formatted the way they appear in the data.
- Be direct about what is flagged, if anything is.
- This is analysis of their own figures, not regulated financial advice - \
you should not add a disclaimer, the application shows one already."""

_LOCALIZE_SYSTEM = """You are a professional financial translator. Translate \
every string value in the JSON object you are given from English to \
natural Polish financial language.

Rules you must follow:
- Keep the same JSON keys and the same array lengths as given - never add, \
remove or rename a key, and never add or drop an array item.
- Leave any number, percentage, date or currency amount inside a string \
exactly as it is.
- Keep Markdown formatting (headings, bullets, bold) exactly as it is - \
translate only the prose around it.
- Output only the JSON object. Do not add commentary, notes or a preamble."""


# --- Polish localisation of `data` ------------------------------------

# profile/next_steps render prose straight out of `data` (pills aside, which
# stay on the enum values and are translated client-side by i18n) - unlike
# digest and the wallet report, that prose never passes through
# assessment.translate_to_polish. This mirrors that translation step, but
# scoped to only the prose fields, in one call, so enums/keys/numbers can
# never be touched by the model doing the translating.

def _profile_translatable(data: dict) -> dict:
    return {
        "summary_md": data["summary_md"],
        "priorities": list(data["priorities"]),
        "mismatches": [
            {
                "about": m["about"],
                "stated": m["stated"],
                "actual": m["actual"],
                "why_it_matters": m["why_it_matters"],
            }
            for m in data["mismatches"]
        ],
    }


def _merge_profile_translation(data: dict, translated: dict) -> dict:
    merged = copy.deepcopy(data)
    merged["summary_md"] = translated["summary_md"]
    merged["priorities"] = list(translated["priorities"])
    for m, tm in zip(merged["mismatches"], translated["mismatches"]):
        m["about"] = tm["about"]
        m["stated"] = tm["stated"]
        m["actual"] = tm["actual"]
        m["why_it_matters"] = tm["why_it_matters"]
    return merged


def _next_steps_translatable(data: dict) -> dict:
    return {"steps": [{"title": s["title"], "why_md": s["why_md"]} for s in data["steps"]]}


def _merge_next_steps_translation(data: dict, translated: dict) -> dict:
    merged = copy.deepcopy(data)
    for s, ts in zip(merged["steps"], translated["steps"]):
        s["title"] = ts["title"]
        s["why_md"] = ts["why_md"]
    return merged


_LOCALIZABLE = {
    "profile": (_profile_translatable, _merge_profile_translation),
    "next_steps": (_next_steps_translatable, _merge_next_steps_translation),
}


def _json_schema_for(value) -> dict:
    """A json_schema fragment shaped like `value`, for the translation
    request's response_format - built from the payload itself so it always
    matches, rather than hand-maintaining a schema per kind."""
    if isinstance(value, list):
        items = _json_schema_for(value[0]) if value else {"type": "string"}
        return {"type": "array", "items": items}
    if isinstance(value, dict):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {k: _json_schema_for(v) for k, v in value.items()},
            "required": list(value.keys()),
        }
    return {"type": "string"}


def _validate_translation_shape(original, translated) -> bool:
    """Same keys, same array lengths, every leaf a string - checked
    recursively rather than trusting response_format, because not every
    model behind the router enforces the schema it was given."""
    if isinstance(original, dict):
        return (
            isinstance(translated, dict)
            and set(translated.keys()) == set(original.keys())
            and all(_validate_translation_shape(v, translated[k]) for k, v in original.items())
        )
    if isinstance(original, list):
        return (
            isinstance(translated, list)
            and len(translated) == len(original)
            and all(_validate_translation_shape(o, t) for o, t in zip(original, translated))
        )
    return isinstance(translated, str)


def localize_data(data: dict, kind: str) -> tuple[dict | None, str | None]:
    """Translate only `data`'s prose fields to Polish in one call, leaving
    enums, keys and numbers untouched. Returns (data_localized, failure
    reason) - never raises, because the English `data` and `content` have
    already made the job usable and a translation problem should degrade to
    a UI note rather than fail the whole insight."""
    extract, merge = _LOCALIZABLE[kind]
    payload = extract(data)
    schema = {"name": "localized_prose", "schema": _json_schema_for(payload)}
    try:
        text = _complete_json(
            settings.llm_translate_model, _LOCALIZE_SYSTEM, json.dumps(payload), schema,
        )
        translated = _first_json_object(text)
    except (llm.LLMUnavailable, ValueError) as exc:
        return None, f"could not translate the structured result: {exc}"

    if not _validate_translation_shape(payload, translated):
        return None, "translation returned an unexpected shape"

    return merge(data, translated), None


# --- Questionnaire --------------------------------------------------------

def load_profile_answers(db: Session) -> ProfileAnswers:
    row = db.query(Setting).filter(Setting.key == _PROFILE_ANSWERS_KEY).first()
    if not row or not row.value:
        return ProfileAnswers()
    return ProfileAnswers.model_validate(json.loads(row.value))


def save_profile_answers(db: Session, answers: ProfileAnswers) -> None:
    row = db.query(Setting).filter(Setting.key == _PROFILE_ANSWERS_KEY).first()
    payload = answers.model_dump_json()
    if row is None:
        db.add(Setting(key=_PROFILE_ANSWERS_KEY, value=payload))
    else:
        row.value = payload
    db.commit()


# --- Shared plumbing -------------------------------------------------------

def _complete_json(model: str, system: str, user: str, response_format: dict) -> str:
    """One structured completion, retried once without `response_format`
    when the server does not understand it - see llm.complete's docstring."""
    try:
        return llm.complete(
            model, system, user, temperature=0.2,
            max_tokens=settings.llm_max_tokens, response_format=response_format,
        )
    except llm.LLMUnavailable:
        return llm.complete(
            model, system, user, temperature=0.2, max_tokens=settings.llm_max_tokens,
        )


def _first_json_object(text: str) -> dict:
    """The first top-level JSON object in `text`.

    Even with response_format requested, a model can still wrap its answer
    in a code fence or a sentence - this walks past any of that rather than
    requiring the whole response to be exactly one JSON document.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("model did not return a JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    return obj


def _default_digest_period(db: Session) -> str:
    from .budget import month_key, shift_month
    from ..routes.helpers import today_in

    today = today_in(db)
    return shift_month(month_key(today), -1)


# --- Profile ---------------------------------------------------------------

def build_profile_snapshot(db: Session) -> dict:
    from ..models.income import IncomeSource
    from ..routes.expenses import expense_summary
    from ..routes.fire import get_fire
    from ..routes.helpers import get_base_currency, get_features, today_in
    from ..routes.statistics import allocation as allocation_route
    from ..services.income import is_active_in_month
    from .budget import month_key

    answers = load_profile_answers(db)
    features = get_features(db)
    today = today_in(db)
    month = month_key(today)

    sources = db.query(IncomeSource).all()
    active_kinds = {s.kind for s in sources if is_active_in_month(s, month)}
    if "uop" in active_kinds and "b2b" in active_kinds:
        income_stability = "mixed"
    elif active_kinds:
        income_stability = next(iter(active_kinds - {"other"}), "other")
    else:
        income_stability = "none"

    committed = expense_summary(db=db).monthly_total

    # Portfolio off => no allocation to profile against; skip that whole side
    # rather than showing a "revealed risk" read off assets nobody tracks.
    if features.portfolio:
        alloc = allocation_route(db=db)
        base_currency = alloc["base_currency"]
        safe_total = next(
            (b["value"] for b in alloc["by_profile"] if b["profile"] == "safe"), 0.0
        )
        runway_months = round(safe_total / committed, 1) if committed else None
        crypto = next((c for c in alloc["by_category"] if c["category"] == "Crypto"), None)
        crypto_share_pct = crypto["percent"] if crypto else 0.0
        wrapper_value = sum(i["value"] for i in alloc["items"] if i.get("wrapper"))
        wrapper_share_pct = (
            round(100.0 * wrapper_value / alloc["total"], 2) if alloc["total"] else 0.0
        )
        revealed_risk_inputs = {
            "by_band": alloc["by_profile"],
            "crypto_share_pct": crypto_share_pct,
            "wrapper_share_pct": wrapper_share_pct,
        }
    else:
        base_currency = get_base_currency(db)
        runway_months = None
        revealed_risk_inputs = None

    # Fire off => no FI progress to report.
    fi_progress = None
    if features.fire:
        fire_payload = get_fire(db=db)
        result = fire_payload.get("result")
        fi_progress = result.get("progress") if result else None

    return {
        "base_currency": base_currency,
        "answers": answers.model_dump(),
        "risk_capacity_inputs": {
            "income_stability": income_stability,
            "runway_months": runway_months,
            "fi_progress_pct": round(fi_progress * 100, 1) if fi_progress is not None else None,
            "dependents": answers.dependents,
        },
        "revealed_risk_inputs": revealed_risk_inputs,
    }


def render_profile_snapshot(snap: dict) -> str:
    out = ["# This person, as their own data shows it\n"]

    out.append("## Questionnaire answers")
    for k, v in snap["answers"].items():
        out.append(f"- {k}: {v}")
    out.append("")

    out.append("## Risk capacity - deterministic inputs")
    cap = snap["risk_capacity_inputs"]
    out.append(f"- Income stability: {cap['income_stability']}")
    out.append(
        f"- Safe-asset runway: {cap['runway_months']} months of committed spend"
        if cap["runway_months"] is not None else "- Safe-asset runway: not computable (no committed spend)"
    )
    out.append(
        f"- FI progress: {cap['fi_progress_pct']}%"
        if cap["fi_progress_pct"] is not None else "- FI progress: FIRE not configured"
    )
    out.append(f"- Dependents: {cap['dependents'] if cap['dependents'] is not None else 'not answered'}")
    out.append("")

    out.append("## Revealed risk - current allocation")
    rev = snap["revealed_risk_inputs"]
    if rev is None:
        out.append("- Portfolio tracking is off - no allocation to read.")
    else:
        for b in rev["by_band"]:
            out.append(f"- {b['profile']}: {b['percent']:.1f}%")
        out.append(f"- Crypto share: {rev['crypto_share_pct']:.1f}%")
        out.append(f"- Tax-advantaged wrapper share: {rev['wrapper_share_pct']:.1f}%")
    return "\n".join(out)


def _render_profile_markdown(r: ProfileResult) -> str:
    out = ["## Summary", r.summary_md.strip(), ""]
    out += [
        "## Stated vs capacity vs revealed",
        f"- Stated tolerance: {r.stated_tolerance}",
        f"- Risk capacity: {r.capacity}",
        f"- Revealed risk: {r.revealed}",
        "",
        "## Mismatches",
    ]
    if r.mismatches:
        for m in r.mismatches:
            out.append(f"- {m.about}: stated {m.stated}, actual {m.actual} - {m.why_it_matters}")
    else:
        out.append("- None found.")
    out += ["", "## Priorities"]
    if r.priorities:
        for p in r.priorities:
            out.append(f"- {p}")
    else:
        out.append("- None given.")
    out.append("")
    out.append(f"Suggested wallet-assessment style: {r.suggested_style.replace('_', ' ')}")
    return "\n".join(out)


def run_profile(snapshot: dict) -> tuple[dict, str, str]:
    """Ask Thinker to profile this person. Returns (data, content_en, model)."""
    model = settings.llm_model
    response_format = {"type": "json_schema", "json_schema": PROFILE_JSON_SCHEMA}
    text = _complete_json(model, _PROFILE_SYSTEM, render_profile_snapshot(snapshot), response_format)
    result = ProfileResult.model_validate(_first_json_object(text))
    return result.model_dump(), _render_profile_markdown(result), model


# --- Digest ------------------------------------------------------------

def build_digest_snapshot(db: Session, period: str) -> dict:
    from ..models.position import Position
    from ..routes import monthly as monthly_routes
    from ..routes.fire import get_fire
    from ..routes.helpers import get_features, today_in
    from .budget import wallet_window

    today = today_in(db)
    features = get_features(db)
    month_out = monthly_routes.get_month(period, db=db)
    hist = monthly_routes.analytics(months_back=12, months_ahead=0, db=db)
    rungs = ladder.build_ladder(db)

    effective_hist = [
        p.effective for p in hist.timeline if p.month != period and p.effective is not None
    ]
    median_effective = statistics.median(effective_hist) if effective_hist else None

    # Portfolio off => no flows/market-movement split to report.
    flows = 0.0
    market_change = None
    if features.portfolio:
        window = wallet_window(period, today)
        if window is not None and month_out.wallet_change is not None:
            start, end = window
            positions = db.query(Position).all()
            flows = sum(
                float(p.flow_in_base) for p in positions
                if p.flow_in_base is not None and start < p.timestamp.date() <= end
            )
            market_change = round(month_out.wallet_change - flows, 2)

    # Fire off => no FI progress to report.
    fi_progress = None
    years_to_fi = None
    if features.fire:
        fire_payload = get_fire(db=db)
        result = fire_payload.get("result")
        fi_progress = result.get("progress") if result else None
        years_to_fi = result.get("simulate", {}).get("years") if result else None

    spend_figure = (
        month_out.effective_spent if month_out.effective_spent is not None else month_out.actual_spent
    )
    anomalies: list[dict] = []
    if median_effective and spend_figure is not None and spend_figure > 1.3 * median_effective:
        anomalies.append({
            "key": "spend_spike",
            "detail": (
                f"This month's spend is {spend_figure:.2f}, more than 1.3x the "
                f"12-month median of {median_effective:.2f}."
            ),
        })
    if month_out.effective_spent is not None and month_out.actual_spent:
        gap = abs(month_out.effective_spent - month_out.actual_spent) / month_out.actual_spent
        if gap > 0.2:
            anomalies.append({
                "key": "typed_effective_gap",
                "detail": (
                    f"Typed spend {month_out.actual_spent:.2f} vs effective spend "
                    f"{month_out.effective_spent:.2f} - a {gap * 100:.1f}% gap."
                ),
            })
    envelope_rung = next((r for r in rungs if r["key"] == "envelope_covered"), None)
    if envelope_rung and envelope_rung["status"] == "todo":
        anomalies.append({
            "key": "envelope_not_covered",
            "detail": "Safe assets do not yet cover the outstanding B2B tax set-aside.",
        })
    data_fresh_rung = next((r for r in rungs if r["key"] == "data_fresh"), None)
    if data_fresh_rung and data_fresh_rung["status"] != "done":
        anomalies.append({
            "key": "stale_data",
            "detail": "Some assets or recent months are not up to date.",
        })

    return {
        "period": period,
        "base_currency": month_out.base_currency,
        "income_sources": month_out.income_sources,
        "income_total": month_out.income_in_base,
        "typed_spend": month_out.actual_in_base,
        "effective_spend": month_out.effective_spent,
        "savings_rate": month_out.savings_rate,
        "avg_savings_rate_12m": hist.avg_savings_rate,
        "wallet_change": month_out.wallet_change,
        "flows": round(flows, 2),
        "market_change": market_change,
        "fi_progress_pct": round(fi_progress * 100, 1) if fi_progress is not None else None,
        "years_to_fi": years_to_fi,
        "ladder": [{"key": r["key"], "status": r["status"], "figures": r["figures"]} for r in rungs],
        "anomalies": anomalies,
        # Tells render_digest_snapshot whether to write the portfolio/FIRE
        # sections at all, rather than let them print "not recorded" for
        # figures nobody chose to track.
        "portfolio_enabled": features.portfolio,
        "fire_enabled": features.fire,
    }


def render_digest_snapshot(snap: dict) -> str:
    cur = snap["base_currency"]

    def money(v):
        return f"{v:,.2f} {cur}" if v is not None else "not recorded"

    out = [f"# {snap['period']} at a glance\n", "## Income by source"]
    if snap["income_sources"]:
        for s in snap["income_sources"]:
            out.append(f"- {s['name']} ({s['kind']}): {money(s['net_in_base'])}")
    else:
        out.append("- No income sources recorded.")
    out.append(f"\nTotal net income: {money(snap['income_total'])}\n")

    out.append("## Spending")
    out.append(f"Typed spend: {money(snap['typed_spend'])}")
    out.append(f"Effective spend (income minus portfolio change): {money(snap['effective_spend'])}")
    out.append(
        f"Savings rate this month: {snap['savings_rate']}%"
        if snap["savings_rate"] is not None else "Savings rate this month: not available"
    )
    if snap["avg_savings_rate_12m"] is not None:
        out.append(f"Average savings rate, trailing 12 months: {snap['avg_savings_rate_12m']}%")
    out.append("")

    out.append("## Portfolio change")
    if not snap.get("portfolio_enabled", True):
        out.append("Portfolio tracking is off - this person does not record assets.")
    else:
        out.append(f"Total change: {money(snap['wallet_change'])}")
        out.append(f"From flows (money moved in/out): {money(snap['flows'])}")
        out.append(f"From market movement: {money(snap['market_change'])}")
    out.append("")

    out.append("## FIRE progress")
    if not snap.get("fire_enabled", True):
        out.append("FIRE tracking is off for this person.")
    else:
        out.append(
            f"Progress to FI target: {snap['fi_progress_pct']}%"
            if snap["fi_progress_pct"] is not None else "FIRE is not configured."
        )
        if snap["years_to_fi"] is not None:
            out.append(f"Years to FI at current pace: {snap['years_to_fi']}")
    out.append("")

    out.append("## Ladder status")
    for r in snap["ladder"]:
        out.append(f"- {r['key']}: {r['status']}")
    out.append("")

    out.append("## Flagged")
    if snap["anomalies"]:
        for a in snap["anomalies"]:
            out.append(f"- {a['key']}: {a['detail']}")
    else:
        out.append("- Nothing flagged.")
    return "\n".join(out)


def run_digest(snapshot: dict) -> tuple[str, str]:
    """Ask Thinker for the digest text. Returns (content_en, model)."""
    model = settings.llm_model
    system = _DIGEST_SYSTEM.format(currency=snapshot["base_currency"])
    text = llm.complete(
        model, system, render_digest_snapshot(snapshot),
        temperature=0.3, max_tokens=settings.llm_max_tokens,
    )
    return text, model


# --- Next steps --------------------------------------------------------

def build_next_steps_snapshot(db: Session) -> dict:
    from ..models.insight import Insight

    rungs = ladder.build_ladder(db)
    feedback = ladder.active_feedback(db)
    candidates = [
        {"key": r["key"], "status": r["status"], "figures": r["figures"]}
        for r in rungs
        if r["status"] in ("todo", "in_progress", "unknown")
        and feedback.get(r["key"], {}).get("state") not in ("dismissed", "later")
    ]
    profile = (
        db.query(Insight)
        .filter(Insight.kind == "profile", Insight.status == "done")
        .order_by(Insight.created_at.desc())
        .first()
    )
    return {"candidates": candidates, "profile": profile.data if profile else None}


def render_next_steps_snapshot(snap: dict) -> str:
    out = ["# Candidate next steps\n", "Only these keys exist - never rank one not listed here.\n"]
    for c in snap["candidates"]:
        out.append(f"## {c['key']} (status: {c['status']})")
        for k, v in c["figures"].items():
            out.append(f"- {k}: {v}")
        out.append("")
    if snap["profile"]:
        p = snap["profile"]
        out.append("## This person's profile")
        out.append(f"- Stated risk tolerance: {p.get('stated_tolerance')}")
        out.append(f"- Risk capacity: {p.get('capacity')}")
        out.append(f"- Priorities: {', '.join(p.get('priorities') or [])}")
    return "\n".join(out)


def _render_next_steps_markdown(r: NextStepsResult) -> str:
    if not r.steps:
        return "## Next steps\n\nNo outstanding steps were ranked."
    out = []
    for step in r.steps:
        out.append(f"## {step.title}")
        out.append(step.why_md.strip())
        out.append("")
    return "\n".join(out)


def run_next_steps(snapshot: dict) -> tuple[dict, str, str, list[str]]:
    """Ask Thinker to rank the candidates. Returns (data, content_en, model,
    discarded) - `discarded` holds any ranked key that was not a real
    candidate, logged rather than silently dropped."""
    model = settings.llm_model
    response_format = {"type": "json_schema", "json_schema": NEXT_STEPS_JSON_SCHEMA}
    text = _complete_json(
        model, _NEXT_STEPS_SYSTEM, render_next_steps_snapshot(snapshot), response_format
    )
    result = NextStepsResult.model_validate(_first_json_object(text))

    valid_keys = {c["key"] for c in snapshot["candidates"]}
    kept, discarded = [], []
    for step in result.steps:
        (kept if step.key in valid_keys else discarded).append(step)
    ranked = NextStepsResult(steps=kept)
    discarded_notes = [f"unknown step key: {s.key}" for s in discarded]
    return ranked.model_dump(), _render_next_steps_markdown(ranked), model, discarded_notes


# --- Job orchestration -----------------------------------------------------

def generate(db: Session, insight) -> None:
    """Write one insight, start to finish - the same pending -> running ->
    (translating ->) done|failed lifecycle as Report, driven from a worker
    thread by routes/insights.py."""
    try:
        insight.status = "running"
        db.commit()

        extra_ungrounded: list[str] = []
        if insight.kind == "profile":
            snapshot = build_profile_snapshot(db)
            data, content_en, model = run_profile(snapshot)
        elif insight.kind == "digest":
            period = insight.period or _default_digest_period(db)
            insight.period = period
            snapshot = build_digest_snapshot(db, period)
            content_en, model = run_digest(snapshot)
            data = {}
        elif insight.kind == "next_steps":
            snapshot = build_next_steps_snapshot(db)
            data, content_en, model, extra_ungrounded = run_next_steps(snapshot)
        else:
            raise ValueError(f"unknown insight kind {insight.kind!r}")

        insight.snapshot = snapshot
        insight.data = data
        insight.content_en = content_en
        insight.model = model
        insight.ungrounded = extra_ungrounded + grounding.check_grounding(content_en, snapshot)
        db.commit()

        if insight.language == "pl":
            # Stored before translating, so a translation failure leaves a
            # readable English insight behind rather than nothing at all.
            insight.content = content_en
            insight.status = "translating"
            db.commit()
            polish, translator = assessment.translate_to_polish(content_en)
            insight.content = polish
            insight.translator = translator

            if insight.kind in _LOCALIZABLE:
                # profile/next_steps render `data` as prose directly (not
                # through `content`), so it needs its own translation pass.
                # A failure here must not fail a job whose Markdown content
                # already translated fine - it only means the tab falls back
                # to English data with a note, so record it on `error`
                # (still empty at this point for a job reaching "done")
                # rather than raising.
                localized, reason = localize_data(data, insight.kind)
                insight.data_localized = localized
                if reason:
                    insight.error = f"Data translation unavailable: {reason}"
        else:
            insight.content = content_en

        insight.status = "done"
        db.commit()
    except llm.LLMUnavailable as exc:
        insight.status = "failed"
        insight.error = str(exc)
        db.commit()
    except (ValidationError, ValueError, KeyError) as exc:
        # A malformed model answer (bad JSON, a field outside its enum) is
        # not a server-availability problem, but it is just as much a
        # reason the job cannot finish.
        insight.status = "failed"
        insight.error = f"Could not use the model's answer: {exc}"
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive
        insight.status = "failed"
        insight.error = f"Unexpected error: {exc}"
        db.commit()
