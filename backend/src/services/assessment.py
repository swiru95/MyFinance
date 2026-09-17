"""Builds the portfolio snapshot and the prompts that turn it into a report.

Two models are involved, and which does what is deliberate. The assessment is
always *reasoned* in English by the Thinker model, because that is where its
reasoning is strongest and because the financial vocabulary it was trained on
is English. A Polish report is then produced by handing that finished text to
Bielik, a Polish-native model, to translate. Asking Thinker to write Polish
directly gets you worse Polish and worse analysis at the same time.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from . import llm

# What each style treats as a good portfolio. These go into the prompt verbatim,
# so they are written as instructions to the model rather than as UI copy.
STYLE_BRIEFS = {
    "safe": (
        "Capital preservation comes first. Volatility is a cost to be avoided, "
        "not an opportunity. A large cash and bond allocation is correct, not "
        "lazy. Judge concentration in equities, crypto or any single holding "
        "harshly, and expect a cash buffer covering at least six months of "
        "committed spend."
    ),
    "balanced": (
        "Growth matters, but so does sleeping at night. Expect meaningful "
        "equity exposure alongside a real cash buffer of three to six months of "
        "committed spend, with no single asset class dominating the portfolio "
        "and speculative holdings kept to a modest slice."
    ),
    "risky": (
        "Drawdowns are an accepted cost of pursuing returns, and concentration "
        "on conviction is legitimate rather than a mistake. Still insist on a "
        "cash buffer large enough that a bad year never forces a sale at the "
        "bottom, and flag risk that is uncompensated rather than merely large."
    ),
    "long_term": (
        "The horizon is a decade or more. Liquidity and short-term volatility "
        "matter much less than compounding and the drag of fees and idle cash. "
        "Treat a large idle cash position as a real cost, and judge holdings by "
        "whether they still make sense in ten years."
    ),
}

_SYSTEM = """You are a careful personal-finance analyst reviewing one person's \
portfolio. You are given their real figures: current holdings, how those \
holdings have moved over time, their recurring commitments, and what they have \
earned and spent month by month.

The person has told you which style of portfolio they are aiming for. Judge \
what they actually hold against that target, and say plainly where the two \
disagree.

Target style - {style_name}:
{style_brief}

Write the report in English as Markdown, using exactly these sections:

## Summary
Two or three sentences: what this portfolio is, and the single most important \
thing about it right now.

## What stands out
The three to five things that most matter, each as a bullet with the figure \
that supports it.

## Risks
Concrete exposures, each tied to a number from the data. Include concentration, \
the size of the cash buffer against committed spend, and anything whose value \
has moved sharply.

## Recommendations
Specific, ordered actions. Each one names a target - a percentage, an amount, \
or a number of months of cover. Do not recommend specific tickers, funds or \
products.

Rules you must follow:
- Use only the figures given below. Never invent a number, a holding, or a date.
- Quote amounts in {currency}, formatted the way they appear in the data.
- If something the person would expect you to assess is missing from the data, \
say that it is missing rather than guessing at it.
- Be direct. Where the portfolio is wrong for the stated style, say so.
- This is analysis of their own figures, not regulated financial advice, and \
you should not add a disclaimer - the application shows one already."""

_TRANSLATE_SYSTEM = """You are a professional financial translator. Translate \
the user's message from English into Polish.

- Output only the translation. Do not add commentary, notes or a preamble.
- Preserve the Markdown structure exactly: the same headings, the same bullets, \
in the same order.
- Leave every number, percentage, date and currency amount exactly as it is.
- Use natural Polish financial vocabulary, not a word-for-word rendering."""


def _money(value: float, currency: str) -> str:
    """A plain, unambiguous amount for the prompt.

    Deliberately not locale-formatted: a model reading "12 400,00" has to guess
    whether the comma is a decimal point, and it sometimes guesses wrong.
    """
    return f"{value:,.2f} {currency}"


def build_snapshot(db: Session) -> dict:
    """Everything the model is allowed to see, in one structure.

    Assembled from the same endpoints the UI reads, so the report can never
    disagree with what is on screen.
    """
    from ..routes.expenses import expense_summary
    from ..routes.monthly import analytics as monthly_analytics
    from ..routes.statistics import allocation as allocation_route

    alloc = allocation_route(db=db)
    expenses = expense_summary(db=db)
    months = monthly_analytics(months_back=11, months_ahead=0, db=db)

    return {
        "base_currency": alloc["base_currency"],
        "total_value": alloc["total"],
        "holdings": [
            {
                "name": i["name"],
                "category": i["category"],
                "value": i["value"],
                "percent": i["percent"],
            }
            for i in sorted(alloc["items"], key=lambda i: i["value"], reverse=True)
        ],
        "by_category": alloc["by_category"],
        "by_profile": alloc["by_profile"],
        "monthly_committed": expenses.monthly_total,
        "committed_by_category": [
            {"category": c["category"], "total": c["total"]}
            for c in expenses.by_category
        ],
        "months": [
            {
                "month": p.month,
                "committed": p.committed,
                "income": p.income,
                "actual": p.actual,
                "effective": p.effective,
            }
            for p in months.timeline
        ],
        "avg_savings_rate": months.avg_savings_rate,
        "avg_effective_spend": months.avg_effective,
    }


def render_snapshot(snap: dict) -> str:
    """The snapshot as text for the prompt.

    Laid out as headed tables rather than handed over as JSON: the same figures
    in prose-shaped tables get read more reliably, and braces invite the model
    to answer in JSON too.
    """
    cur = snap["base_currency"]
    out: list[str] = []

    out.append(f"# Portfolio as it stands\n")
    out.append(f"Total value: {_money(snap['total_value'], cur)}")
    out.append(f"Reporting currency: {cur}\n")

    out.append("## Holdings")
    if snap["holdings"]:
        for h in snap["holdings"]:
            out.append(
                f"- {h['name']} ({h['category']}): "
                f"{_money(h['value'], cur)}, {h['percent']:.1f}% of the portfolio"
            )
    else:
        out.append("- No holdings recorded.")
    out.append("")

    out.append("## By asset class")
    for g in snap["by_category"]:
        out.append(
            f"- {g['category']}: {_money(g['value'], cur)}, {g['percent']:.1f}%"
            f" ({g['assets']} holding(s))"
        )
    out.append("")

    out.append("## By risk and liquidity band")
    out.append(
        "Bands are: safe, moderate, risky, illiquid. Illiquid means hard to "
        "sell quickly, not necessarily volatile."
    )
    for b in snap["by_profile"]:
        out.append(
            f"- {b['profile']}: {_money(b['value'], cur)}, {b['percent']:.1f}%"
            f" (classes: {', '.join(b['categories']) or 'none'})"
        )
    out.append("")

    out.append("## Recurring commitments")
    out.append(
        f"Total committed every month: {_money(snap['monthly_committed'], cur)}"
    )
    for c in snap["committed_by_category"]:
        out.append(f"- {c['category']}: {_money(c['total'], cur)} per month")
    out.append("")

    out.append("## Month by month")
    out.append(
        "Committed is what the recurring expenses add up to. Income and "
        "Actual are what the person recorded. Effective spend is income minus "
        "the change in total portfolio value over that month, so it captures "
        "spending that was never recorded as an expense - but it also counts a "
        "fall in market value as if it had been spent."
    )
    out.append("")
    out.append("| Month | Committed | Income | Actual | Effective spend |")
    out.append("|---|---|---|---|---|")
    for m in snap["months"]:
        def cell(v):
            return _money(v, cur) if v is not None else "not recorded"

        out.append(
            f"| {m['month']} | {_money(m['committed'], cur)} | {cell(m['income'])} "
            f"| {cell(m['actual'])} | {cell(m['effective'])} |"
        )
    out.append("")

    if snap["avg_savings_rate"] is not None:
        out.append(f"Average savings rate: {snap['avg_savings_rate']:.1f}%")
    if snap["avg_effective_spend"] is not None:
        out.append(
            f"Average effective spend: {_money(snap['avg_effective_spend'], cur)}"
        )
    return "\n".join(out)


def write_report(snap: dict, style: str) -> tuple[str, str]:
    """Produce the English assessment. Returns (text, model name)."""
    brief = STYLE_BRIEFS.get(style, STYLE_BRIEFS["balanced"])
    system = _SYSTEM.format(
        style_name=style.replace("_", "-"),
        style_brief=brief,
        currency=snap["base_currency"],
    )
    model = settings.llm_model
    return (
        llm.complete(
            model,
            system,
            render_snapshot(snap),
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
        ),
        model,
    )


def translate_to_polish(text: str) -> tuple[str, str]:
    """Translate a finished report. Returns (text, translating model name)."""
    model = settings.llm_translate_model
    # Headroom over the English: Polish runs longer, and truncating a report
    # mid-sentence is worse than the request costing a little more.
    return (
        llm.complete(
            model,
            _TRANSLATE_SYSTEM,
            text,
            temperature=0.2,
            max_tokens=settings.llm_translate_max_tokens,
        ),
        model,
    )
