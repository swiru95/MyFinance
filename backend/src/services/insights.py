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
                        "about": {
                            "type": "string",
                            "description": (
                                "A short plain-language phrase naming what "
                                "disagrees, e.g. 'risk tolerance' or 'cash "
                                "buffer size' - never a snake_case "
                                "identifier or field name."
                            ),
                        },
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
- Each mismatch's "about" is a short plain-language phrase a person would \
say out loud, e.g. "risk tolerance" or "how much cash you keep spare" - \
never a snake_case identifier, a field name, or a copy of a key from the \
data you were given.
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
Exactly one action. Tie it to one flagged item or ladder line given below by \
its plain-language description, and say what to actually do about it.

Rules you must follow:
- Use only the figures given below. Never invent a number.
- Quote amounts in {currency}, formatted the way they appear in the data.
- Be direct about what is flagged, if anything is.
- Refer to ladder lines and flagged items only by the plain-language \
description given for them - never quote an internal key or field name \
(e.g. write "stale data", never "stale_data").
- This is analysis of their own figures, not regulated financial advice - \
you should not add a disclaimer, the application shows one already."""

_LOCALIZE_SYSTEM = """You are a professional financial translator. You are \
given a JSON array of English strings. Translate each one to natural \
Polish financial language and answer with a JSON array of the same length, \
in the same order - one translated string per input string.

Rules you must follow:
- Return exactly as many strings as you were given, in the same order - \
never add, remove, merge or reorder items.
- Leave any number, percentage, date or currency amount inside a string \
exactly as it is.
- Keep Markdown formatting (headings, bullets, bold) exactly as it is - \
translate only the prose around it.
- Output only the JSON array. Do not add commentary, notes or a preamble."""

_LOCALIZE_LEAF_SYSTEM = """You are a professional financial translator. \
Translate the user's message from English to natural Polish financial \
language.

Rules you must follow:
- Leave any number, percentage, date or currency amount exactly as it is.
- Keep Markdown formatting (headings, bullets, bold) exactly as it is - \
translate only the prose around it.
- Output only the translation. Do not add commentary, notes or a preamble."""


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


def _flatten_strings(value) -> list[str]:
    """Every leaf string in `value`, depth-first, in the order a plain walk
    of dicts (by insertion order) and lists visits them - the same order
    `_unflatten_strings` reads them back in, so the two are always used as a
    matched pair over the same-shaped `value`."""
    if isinstance(value, dict):
        out: list[str] = []
        for v in value.values():
            out.extend(_flatten_strings(v))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_flatten_strings(v))
        return out
    return [value]


def _unflatten_strings(value, strings: list[str], cursor: list[int]):
    """Rebuild a structure shaped like `value`, with each leaf replaced by
    the next string from `strings` (consumed in `_flatten_strings` order).
    `cursor` is a one-element list used as a mutable position across the
    recursion, since plain ints don't mutate through a call."""
    if isinstance(value, dict):
        return {k: _unflatten_strings(v, strings, cursor) for k, v in value.items()}
    if isinstance(value, list):
        return [_unflatten_strings(v, strings, cursor) for v in value]
    s = strings[cursor[0]]
    cursor[0] += 1
    return s


def _first_json_array(text: str) -> list:
    """The first top-level JSON array in `text` - see _first_json_object,
    which this mirrors for the array-shaped translation response."""
    start = text.find("[")
    if start == -1:
        raise ValueError("model did not return a JSON array")
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(obj, list):
        raise ValueError("model did not return a JSON array")
    return obj


def _translate_leaf(model: str, leaf: str) -> str:
    """Translate one string to Polish on its own. Raises LLMUnavailable if
    the model is unreachable (timeout, connection error, 5xx), which stops
    the per-leaf loop; other failures return an empty string so that a
    single stubborn leaf never fails the whole fallback."""
    try:
        return llm.complete(
            model, _LOCALIZE_LEAF_SYSTEM, leaf,
            temperature=0.2, max_tokens=settings.llm_translate_max_tokens,
        ).strip()
    except llm.LLMUnavailable:
        raise
    except Exception:
        # Any other error (malformed response, etc.) - fall back to English
        # for this leaf only, don't stop the whole per-leaf loop.
        return ""


def _translate_leaves_individually(model: str, leaves: list[str]) -> tuple[list[str], int]:
    """One small request per string rather than one big structured one -
    the fallback when the bulk array call comes back the wrong shape.
    Returns (translated leaves, how many fell back to their English
    original because that individual request also failed). Stops at the
    first LLMUnavailable (model is down) and keeps English for remaining."""
    out: list[str] = []
    failures = 0
    for i, leaf in enumerate(leaves):
        try:
            translated = _translate_leaf(model, leaf)
            if not translated:
                failures += 1
                out.append(leaf)
            else:
                out.append(translated)
        except llm.LLMUnavailable:
            # Model became unavailable; keep English for this and remaining leaves
            out.append(leaf)
            out.extend(leaves[i + 1:])
            # Count the unavailable ones as failures so localize_data
            # knows the result is not fully localized.
            failures += len(leaves) - i
            break
    return out, failures


def localize_data(data: dict, kind: str) -> tuple[dict | None, str | None]:
    """Translate only `data`'s prose fields to Polish, leaving enums, keys
    and numbers untouched. Returns (data_localized, note) - never raises,
    because the English `data` and `content` have already made the job
    usable and a translation problem should degrade to a UI note rather
    than fail the whole insight.

    The prose is sent as a flat JSON array of strings rather than as an
    object mirroring `data`'s own keys: a model translating a nested object
    has been observed translating (or otherwise mangling) the *keys* too,
    which then fails validation and loses the whole translation. An array
    has no keys to mangle, and position - not a key - says which leaf is
    which, so `_unflatten_strings` can always put the answer back in the
    right place as long as the length matches.

    If that bulk call comes back malformed (wrong length, not a JSON array),
    this falls back to translating each string on its own rather than giving
    up on the whole thing. If the server is unreachable (LLMUnavailable),
    gives up immediately with no per-leaf fallback. `note` is only ever set
    when at least one string could not be translated at all, not merely
    because the bulk attempt needed the fallback.
    """
    extract, merge = _LOCALIZABLE[kind]
    payload = extract(data)
    leaves = _flatten_strings(payload)
    if not leaves:
        return merge(data, payload), None

    model = settings.llm_translate_model
    schema = {"name": "localized_strings", "schema": {"type": "array", "items": {"type": "string"}}}

    translated_leaves: list[str] | None = None
    bulk_failure: str | None = None
    try:
        text = _complete_json(model, _LOCALIZE_SYSTEM, json.dumps(leaves), schema)
        candidate = _first_json_array(text)
        if len(candidate) == len(leaves) and all(isinstance(s, str) for s in candidate):
            translated_leaves = candidate
        else:
            # Wrong shape from the model; try per-leaf fallback
            bulk_failure = "translation returned an unexpected shape"
    except llm.LLMUnavailable as exc:
        # Model is down (timeout, connection error, 5xx); don't retry per-leaf
        return None, f"could not reach the model server: {exc}"
    except ValueError as exc:
        # JSON parsing or other shape error; try per-leaf fallback
        bulk_failure = f"could not translate the structured result: {exc}"

    note = None
    if translated_leaves is None:
        try:
            translated_leaves, failures = _translate_leaves_individually(model, leaves)
            if failures == len(leaves):
                return None, bulk_failure or "could not translate individual strings"
            if failures:
                note = f"{failures} of {len(leaves)} strings could not be translated and are shown in English"
        except llm.LLMUnavailable as exc:
            # This shouldn't happen (per-leaf stops on first unavailable),
            # but if it does, give up rather than retry.
            return None, f"model became unavailable during per-leaf translation: {exc}"

    translated = _unflatten_strings(payload, translated_leaves, [0])
    return merge(data, translated), note


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
    only when the server rejected the request outright (HTTP 4xx, e.g. it
    does not understand `response_format`) - see llm.LLMBadRequest.

    A timeout or connection failure (the base LLMUnavailable) is deliberately
    not retried here: the caller already waited out settings.llm_timeout
    once, and retrying would silently double an already-minutes-long wait
    instead of surfacing the failure - see llm.complete's docstring.
    """
    try:
        return llm.complete(
            model, system, user, temperature=0.2,
            max_tokens=settings.llm_max_tokens, response_format=response_format,
        )
    except llm.LLMBadRequest:
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
    """The month a digest opens on when none was requested: the current
    calendar month, not the last completed one - a person who only started
    using the app this month still wants "this month at a glance", not a
    guaranteed-empty prior month with no MonthlyRecord (see
    build_digest_snapshot for how that empty month is now represented)."""
    from .budget import month_key
    from ..routes.helpers import today_in

    return month_key(today_in(db))


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

# Human-readable labels for the ladder's rung keys and the digest's own
# anomaly keys, for the digest prompt only - services/ladder.py's RUNG_KEYS
# and this function's own anomaly keys are internal identifiers, and hand
# ing one to the model as if it were prose got it echoed back verbatim (a
# headline that read "stale_data"), which the Polish translator then further
# mangled into something like "stale_dane" since it had no way to know the
# word was not meant to be translated. Mirrors the (untranslated, English)
# copy in frontend/src/lib/strings/insights.ts's `ins.ladder.<key>.title`.
_RUNG_LABELS = {
    "starter_buffer": "Starter buffer",
    "envelope_covered": "Tax envelope covered",
    "emergency_fund": "Emergency fund",
    "ppk_on": "PPK contributions",
    "ikze_used": "IKZE allowance",
    "ike_used": "IKE allowance",
    "fire_configured": "FIRE plan set up",
    "savings_rate_on_track": "Savings rate on track",
    "data_fresh": "Data up to date",
}

_ANOMALY_LABELS = {
    "spend_spike": "Spend spike",
    "typed_effective_gap": "Typed vs effective spend gap",
    "envelope_not_covered": "Tax envelope not covered",
    "stale_data": "Data needs updating",
}


def _rung_label(key: str) -> str:
    return _RUNG_LABELS.get(key, key.replace("_", " "))


def _anomaly_label(key: str) -> str:
    return _ANOMALY_LABELS.get(key, key.replace("_", " "))


def build_digest_snapshot(db: Session, period: str) -> dict:
    from ..models.position import Position
    from ..routes import monthly as monthly_routes
    from ..routes.fire import get_fire
    from ..routes.helpers import get_features, today_in
    from ..routes.statistics import allocation as allocation_route
    from .budget import wallet_window

    today = today_in(db)
    features = get_features(db)
    month_out = monthly_routes.get_month(period, db=db)
    hist = monthly_routes.analytics(months_back=12, months_ahead=0, db=db)
    rungs = ladder.build_ladder(db)

    # No MonthlyRecord for this month at all (`saved`) means nobody typed a
    # spend figure into it - not that they spent nothing. Left as the
    # record's own 0.0 defaults, this used to reach the model (and the
    # DigestTab snapshot table) as "typed spend: 0.00" and "savings rate:
    # 100%", which is actively wrong rather than merely unhelpful - a month
    # that was never recorded needs to say so, not claim a number.
    typed_spend = month_out.actual_in_base if month_out.saved else None
    savings_rate = month_out.savings_rate if month_out.saved else None

    effective_hist = [
        p.effective for p in hist.timeline if p.month != period and p.effective is not None
    ]
    median_effective = statistics.median(effective_hist) if effective_hist else None

    # Portfolio off => no flows/market-movement split, and no holdings to
    # summarise.
    flows = 0.0
    market_change = None
    holdings_summary = None
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

        alloc = allocation_route(db=db)
        top_holdings = sorted(alloc["items"], key=lambda i: i["value"], reverse=True)[:5]
        holdings_summary = {
            "total_value": alloc["total"],
            "top_holdings": [
                {"name": h["name"], "category": h["category"], "value": h["value"], "percent": h["percent"]}
                for h in top_holdings
            ],
            "by_category": [
                {"category": c["category"], "value": c["value"], "percent": c["percent"]}
                for c in alloc["by_category"]
            ],
        }

    # Fire off => no FI progress to report.
    fi_progress = None
    years_to_fi = None
    if features.fire:
        fire_payload = get_fire(db=db)
        result = fire_payload.get("result")
        fi_progress = result.get("progress") if result else None
        years_to_fi = result.get("simulate", {}).get("years") if result else None

    spend_figure = (
        month_out.effective_spent if month_out.effective_spent is not None else typed_spend
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
        "recorded": month_out.saved,
        "typed_spend": typed_spend,
        "effective_spend": month_out.effective_spent,
        "savings_rate": savings_rate,
        "avg_savings_rate_12m": hist.avg_savings_rate,
        "committed": month_out.committed,
        "committed_by_category": month_out.by_category,
        "breakdown": month_out.breakdown,
        "commitments_paid_total": month_out.commitments_paid_total,
        "other_spent": month_out.other_spent,
        "wallet_change": month_out.wallet_change,
        "flows": round(flows, 2),
        "market_change": market_change,
        "holdings_summary": holdings_summary,
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

    out = [f"# {snap['period']} at a glance\n"]
    if not snap.get("recorded", True):
        out.append(
            "No figures were saved for this month yet (no MonthlyRecord) - "
            "typed spend and this month's savings rate are not recorded "
            "below, not zero.\n"
        )

    out.append("## Income by source")
    if snap["income_sources"]:
        for s in snap["income_sources"]:
            out.append(f"- {s['name']} ({s['kind']}): {money(s['net_in_base'])}")
    else:
        out.append("- No income sources recorded.")
    out.append(f"\nTotal net income: {money(snap['income_total'])}\n")

    out.append("## Committed spending")
    out.append(f"Committed this month: {money(snap.get('committed'))}")
    for c in snap.get("committed_by_category") or []:
        out.append(f"- {c['category']}: {money(c['total'])}")
    out.append("")

    out.append("## Spending")
    out.append(f"Typed spend: {money(snap['typed_spend'])}")
    if snap.get("breakdown"):
        out.append(f"- Of which recurring commitments paid: {money(snap.get('commitments_paid_total'))}")
        out.append(f"- Of which other spending: {money(snap.get('other_spent'))}")
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
        hs = snap.get("holdings_summary")
        if hs:
            out.append(f"Current total portfolio value: {money(hs['total_value'])}")
            if hs["top_holdings"]:
                out.append("Largest holdings:")
                for h in hs["top_holdings"]:
                    out.append(f"- {h['name']} ({h['category']}): {money(h['value'])}, {h['percent']:.1f}%")
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
        out.append(f"- {_rung_label(r['key'])}: {r['status']}")
    out.append("")

    out.append("## Flagged")
    if snap["anomalies"]:
        for a in snap["anomalies"]:
            out.append(f"- {_anomaly_label(a['key'])}: {a['detail']}")
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
    (translating ->) done|failed lifecycle as Report, driven from the shared
    LLM queue's worker by routes/insights.py."""
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
            translator_is_down = False
            try:
                polish, translator = assessment.translate_to_polish(content_en)
                insight.content = polish
                insight.translator = translator
            except llm.LLMBadRequest as exc:
                # Client error (e.g. model doesn't support response_format);
                # try localize_data anyway, might work for simpler requests.
                insight.error = f"Could not translate to Polish, showing English: {exc}"
            except llm.LLMUnavailable as exc:
                # The English content_en already stored above is a complete,
                # useful result - losing it to a translation hiccup would
                # throw away a finished insight over one extra model call,
                # so this degrades to English-with-a-note rather than
                # failing the whole job. Skip localize_data since the
                # translator is down - no point in per-leaf retries either.
                translator_is_down = True
                insight.error = f"Could not translate to Polish, showing English: {exc}"

            if insight.kind in _LOCALIZABLE and not translator_is_down:
                # profile/next_steps render `data` as prose directly (not
                # through `content`), so it needs its own translation pass.
                # A failure here must not fail a job whose Markdown content
                # already translated fine - it only means the tab falls back
                # to English data with a note, so record it alongside
                # `error` (which may already hold the note above) rather
                # than raising.
                localized, note = localize_data(data, insight.kind)
                insight.data_localized = localized
                if note:
                    prefix = "Data translation unavailable" if localized is None else "Data translation incomplete"
                    data_note = f"{prefix}: {note}"
                    insight.error = f"{insight.error} {data_note}".strip() if insight.error else data_note
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
