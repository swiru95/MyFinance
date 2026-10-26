"""Statement import assistant, server side: three narrow jobs for the model.

The browser reads a bank statement itself (frontend/src/lib/import): CSV
columns by name and content, PDF payments by their minus sign, and matches
payments to recurring expenses by amount. It asks for help only with what code
cannot settle, and only when the wallet chose "on the server" in Settings:

- columns:  which CSV column holds the date, amount, description, currency;
- extract:  the payments in a chunk of PDF text that prints debits unsigned;
- match:    which payment pays a recurring expense whose amount varies.

Each job has a fixed prompt and JSON schema here, so the endpoint is not a
general-purpose proxy to the model. The statement text is used for the one
request and never stored or logged. Every answer is checked against the input
before it is returned (column indices in range, only ids that were offered);
the browser checks amounts and dates against the statement text again.
"""
from __future__ import annotations

import json

from ..config import settings
from . import llm

_COLUMNS_SCHEMA = {
    "name": "csv_columns",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "date": {"type": "integer"},
            "amount": {"type": "integer"},
            "debit": {"type": "integer"},
            "credit": {"type": "integer"},
            "outgoing": {"type": "string", "enum": ["negative", "positive"]},
            "description": {"type": "array", "items": {"type": "integer"}, "maxItems": 3},
            "currency": {"type": "integer"},
        },
        "required": ["date", "amount", "debit", "credit", "outgoing", "description", "currency"],
    },
}

_COLUMNS_SYSTEM = (
    "You map the columns of a bank statement CSV. Columns are numbered from 0. Answer with JSON only. "
    "date: the transaction or booking date column. amount: one signed amount column, or -1 if amounts are "
    "split. debit / credit: separate money-out / money-in columns, or -1. outgoing: whether money going out "
    "is printed negative or positive in the amount column. description: up to 3 columns describing the payee "
    "or title. currency: the currency column, or -1. Exact shape: "
    '{"date": 0, "amount": -1, "debit": 3, "credit": 4, "outgoing": "negative", "description": [1], "currency": -1}'
)

_EXTRACT_SCHEMA = {
    "name": "statement_payments",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "transactions": {
                "type": "array",
                "maxItems": 40,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "line": {"type": "integer"},
                        "date": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"},
                        "amount": {"type": "number"},
                        "direction": {"type": "string", "enum": ["out", "in"]},
                        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                        "description": {"type": "string", "maxLength": 80},
                    },
                    "required": ["line", "date", "amount", "direction", "currency", "description"],
                },
            }
        },
        "required": ["transactions"],
    },
}

_EXTRACT_SYSTEM = (
    "You read transactions from the text of a Polish bank statement. Each line starts with its number (L12:). "
    "List every transaction once. line: the number of the line holding its amount. date: the transaction date "
    "as YYYY-MM-DD, exactly as printed (convert the format only). amount: the amount as printed, without a sign. "
    "direction: out for money leaving the account (card payment, transfer out, BLIK, fee, withdrawal), in for "
    "money arriving. currency: as printed, PLN if none. description: the merchant or title, short. Ignore "
    "balances, totals and page headers. Answer with JSON only, exact shape: "
    '{"transactions": [{"line": 12, "date": "2026-10-01", "amount": 45.99, "direction": "out", '
    '"currency": "PLN", "description": "Sklep"}]}'
)

_MATCH_SCHEMA = {
    "name": "commitment_matches",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "commitment": {"type": "integer"},
                        "payment": {"type": "integer"},
                    },
                    "required": ["commitment", "payment"],
                },
            }
        },
        "required": ["matches"],
    },
}

_MATCH_SYSTEM = (
    "You match recurring expenses (rent, utilities, subscriptions, loans) to the payments of one month of a "
    "Polish bank statement. A payment pays an expense when its payee or title names the same company or "
    "service, even if the amount differs a little. For each expense give the id of the paying payment, or -1 "
    "if none clearly pays it. Use a payment at most once. Answer with JSON only, exact shape: "
    '{"matches": [{"commitment": 1, "payment": 10}, {"commitment": 2, "payment": -1}]}'
)


def _ask(system: str, user: str, schema: dict, max_tokens: int) -> dict:
    """One structured answer. Constrained by the schema where the model supports
    it; a model whose grammar sampler cannot take it (Bielik answers 400 "Failed
    to initialize samplers") is asked again without it - the prompts spell out
    the exact shape, and every caller checks the result field by field."""
    ask = lambda rf: llm.complete(  # noqa: E731
        settings.llm_import_model, system, user,
        temperature=0.0, max_tokens=max_tokens, timeout=settings.llm_import_timeout, response_format=rf,
    )
    try:
        text = ask({"type": "json_schema", "json_schema": schema})
    except llm.LLMBadRequest:
        text = ask(None)
    start = text.find("{")
    if start == -1:
        raise ValueError("model did not return a JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text, start)
    return obj


def columns(header: list[str], sample: list[list[str]]) -> dict:
    show = lambda row: " | ".join(f"{i}: {c[:40]}" for i, c in enumerate(row))  # noqa: E731
    user = f"Header: {show(header)}\nRows:\n" + "\n".join(show(r) for r in sample)
    out = _ask(_COLUMNS_SYSTEM, user, _COLUMNS_SCHEMA, 200)
    width = max([len(header)] + [len(r) for r in sample])
    col = lambda v: v if isinstance(v, int) and 0 <= v < width else -1  # noqa: E731
    debit = col(out.get("debit"))
    return {
        "date": col(out.get("date")),
        # Split debit/credit columns win: a model naming both sometimes calls a text column "amount".
        "amount": -1 if debit >= 0 else col(out.get("amount")),
        "debit": debit,
        "credit": col(out.get("credit")),
        "outgoing": "positive" if out.get("outgoing") == "positive" else "negative",
        "description": [c for c in (out.get("description") or [])[:3] if col(c) >= 0],
        "currency": col(out.get("currency")),
    }


def extract(lines: list[str], first_line: int) -> list[dict]:
    user = "\n".join(f"L{first_line + i}: {line}" for i, line in enumerate(lines))
    out = _ask(_EXTRACT_SYSTEM, user, _EXTRACT_SCHEMA, 2000)
    last = first_line + len(lines) - 1
    rows = []
    for t in out.get("transactions") or []:
        if not isinstance(t, dict) or not isinstance(t.get("line"), int):
            continue
        if not first_line <= t["line"] <= last:
            continue
        try:
            amount = abs(float(t.get("amount")))
        except (TypeError, ValueError):
            continue
        rows.append({
            "line": t["line"],
            "date": str(t.get("date", ""))[:10],
            "amount": amount,
            "direction": "in" if t.get("direction") == "in" else "out",
            "currency": str(t.get("currency", "PLN"))[:3].upper(),
            "description": str(t.get("description", ""))[:80],
        })
    return rows


def match(commitments: list[dict], payments: list[dict]) -> list[dict]:
    user = (
        "Recurring expenses:\n"
        + "\n".join(f"id {c['id']}: {c['name']} ({c['category']}), usually {c['amount']:.2f} {c['currency']}"
                    for c in commitments)
        + "\n\nPayments:\n"
        + "\n".join(f"id {p['id']}: {p['date']}  {p['amount']:.2f}  {p['note']}" for p in payments)
    )
    out = _ask(_MATCH_SYSTEM, user, _MATCH_SCHEMA, 40 + 20 * len(commitments))
    commitment_ids = {c["id"] for c in commitments}
    payment_ids = {p["id"] for p in payments}
    used: set[int] = set()
    result = []
    pairs = out.get("matches")
    if pairs is None:
        # Unconstrained models sometimes answer {"<expense id>": <payment id>}.
        pairs = [{"commitment": int(k), "payment": v} for k, v in out.items() if str(k).lstrip("-").isdigit()]
    for m in pairs or []:
        c, p = (m.get("commitment"), m.get("payment")) if isinstance(m, dict) else (None, None)
        if c in commitment_ids and p in payment_ids and p not in used:
            used.add(p)
            commitment_ids.discard(c)
            result.append({"commitment": c, "payment": p})
    return result
