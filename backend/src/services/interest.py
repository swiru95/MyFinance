"""Polish statutory interest (odsetki ustawowe) accrual.

Two bases exist in the Civil Code and they differ by 2 pp:

  * "late"    - odsetki ustawowe za opoznienie, art. 481 par. 2 KC,
                NBP reference rate + 5.5 pp. Owed when a payment is overdue.
  * "capital" - odsetki ustawowe, art. 359 par. 2 KC,
                NBP reference rate + 3.5 pp. Owed on capital where no rate was
                agreed.

Interest is *simple*: art. 482 KC forbids charging interest on overdue interest
except in narrow cases, so nothing compounds here. Days are counted actual/365,
the convention Polish courts use.

The historical rate table below is fixed - past rates never change - and was
verified against nbp.pl's archive. The *current* rate is read live from NBP so
a fresh RPP decision is picked up without editing this file; see
PriceService.nbp_reference_rate.
"""
from __future__ import annotations

from datetime import date

# (in force from, NBP reference rate %). Verified 2026-09-17 against
# https://nbp.pl/podstawowe-stopy-procentowe-archiwum/
NBP_REFERENCE_RATES: list[tuple[date, float]] = [
    (date(2023, 9, 7), 6.00),
    (date(2023, 10, 5), 5.75),
    (date(2025, 5, 8), 5.25),
    (date(2025, 7, 3), 5.00),
    (date(2025, 9, 4), 4.75),
    (date(2025, 10, 9), 4.50),
    (date(2025, 11, 6), 4.25),
    (date(2025, 12, 4), 4.00),
    (date(2026, 3, 5), 3.75),
]

# Margin over the reference rate, in percentage points.
STATUTORY_MARGIN: dict[str, float] = {"late": 5.5, "capital": 3.5}

DAYS_IN_YEAR = 365


def schedule(live: tuple[date, float] | None = None) -> list[tuple[date, float]]:
    """Rate table, extended with a live NBP reading when it is newer."""
    table = list(NBP_REFERENCE_RATES)
    if live:
        when, rate = live
        if when > table[-1][0]:
            table.append((when, rate))
        elif when == table[-1][0] and rate != table[-1][1]:
            table[-1] = (when, rate)
    return table


def periods(
    start: date, end: date, margin: float, live: tuple[date, float] | None = None
) -> list[dict]:
    """Split [start, end) into constant-rate spans.

    Returned so callers can show the working rather than a bare number - for a
    debt in litigation the breakdown is the point.
    """
    if end <= start:
        return []
    table = schedule(live)
    edges = [start] + [d for d, _ in table if start < d < end] + [end]

    def ref_at(day: date) -> float:
        value = table[0][1]
        for when, rate in table:
            if when <= day:
                value = rate
        return value

    out = []
    for begin, finish in zip(edges, edges[1:]):
        days = (finish - begin).days
        if days <= 0:
            continue
        reference = ref_at(begin)
        out.append(
            {
                "from": begin.isoformat(),
                "to": finish.isoformat(),
                "days": days,
                "reference_rate": reference,
                "rate": round(reference + margin, 4),
                "days_in_year": DAYS_IN_YEAR,
            }
        )
    return out


def accrued(
    principal: float,
    start: date,
    end: date,
    margin: float,
    live: tuple[date, float] | None = None,
) -> float:
    """Simple statutory interest on `principal` over [start, end)."""
    total = 0.0
    for p in periods(start, end, margin, live):
        total += principal * (p["rate"] / 100.0) * (p["days"] / DAYS_IN_YEAR)
    return total
