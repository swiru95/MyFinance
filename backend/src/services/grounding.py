"""Checks that every number in the model's text actually appears in the
snapshot it was given.

The model never calculates - see wp-l-llm-insights.md's "Principles" - so any
figure in its text has to trace back to a number we handed it. This never
drops what it cannot match (a false positive here is far cheaper than a
silently invented number); it only reports it, and the caller stores the
list on the insight's `ungrounded` field for the UI to warn about.
"""
from __future__ import annotations

import re

# A number with optional thousand grouping (comma, dot or space) and an
# optional fractional part, optionally followed by a percent sign. Grouping
# and fraction can use either separator - which one is which is worked out
# in _parse_number, because "12,400" (English thousands) and "12,40" (Polish
# decimal) are not distinguishable from the character alone.
_NUM_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[ ,.]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s?(%)?(?!\w)"
)

# A bare four-digit number in a plausible calendar-year range, with no
# grouping or fraction, is essentially always a year or a "YYYY-MM" period
# fragment (dates, headings, the digest's own period) rather than a figure
# that needs to trace back to the snapshot - and snapshots rarely carry raw
# years as numbers, which made these the single biggest source of noise.
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _parse_number(raw: str) -> float:
    """Best-effort float from a matched token, in either EN or PL grouping.

    Spaces are only ever a thousands separator here. Between ',' and '.':
    if both appear, the rightmost is the decimal point and the other is
    grouping; if only one appears, three digits after its last occurrence
    (and only one occurrence) reads as grouping ("12,400"), anything else as
    a decimal point ("12,40", "31.5").
    """
    s = raw.replace(" ", "")
    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        decimal_at = max(s.rfind(","), s.rfind("."))
        decimal_sep = s[decimal_at]
        thousands_sep = "," if decimal_sep == "." else "."
        s = s.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        frac_len = len(s) - s.rfind(sep) - 1
        if s.count(sep) > 1 or frac_len == 3:
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    return float(s)


def _flatten_numbers(obj) -> list[float]:
    """Every numeric leaf of a nested dict/list/tuple, as floats."""
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_numbers(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_flatten_numbers(v))
    return out


def _candidates(snapshot_numbers: list[float]) -> list[float]:
    """Every value a snapshot number could plausibly be written as.

    A fraction (say 0.3104, a savings rate) is legitimately shown in prose
    as "31%" as well as "0.31" - see the spec's "12.3% vs 0.123" tolerance -
    so both the raw value and its x100 form are grounded.
    """
    out: list[float] = []
    for n in snapshot_numbers:
        out.append(n)
        if -1.0 <= n <= 1.0:
            out.append(n * 100)
    return out


def _matches(value: float, candidates: list[float]) -> bool:
    """`value` equals some candidate once both are rounded the same way.

    Tolerates rounding to 0, 1 or 2 dp in either direction - a model that
    writes "31%" for 0.3104 or "12,400" for 12400.37 is not inventing a
    number, it is rounding one we gave it.
    """
    for cand in candidates:
        for dp in (0, 1, 2):
            if round(value, dp) == round(cand, dp):
                return True
    return False


def check_grounding(text: str, snapshot: dict) -> list[str]:
    """Numbers in `text` that cannot be matched to a number in `snapshot`.

    Returns the original substrings (deduplicated, first-seen order) so the
    UI can show the reader what looked unfamiliar, verbatim.
    """
    candidates = _candidates(_flatten_numbers(snapshot))
    ungrounded: list[str] = []
    seen: set[str] = set()

    for m in _NUM_RE.finditer(text):
        raw, pct = m.group(1), m.group(2)
        if pct is None and _YEAR_RE.match(raw):
            continue
        try:
            value = _parse_number(raw)
        except ValueError:
            continue
        check_value = value / 100 if pct else value
        # A percentage is checked both as the fraction it names and as the
        # bare number, so "31%" matches a snapshot value stored either way.
        if _matches(check_value, candidates) or (pct and _matches(value, candidates)):
            continue
        token = m.group(0).strip()
        if token not in seen:
            seen.add(token)
            ungrounded.append(token)
    return ungrounded
