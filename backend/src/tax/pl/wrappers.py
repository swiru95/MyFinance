"""Polish tax-advantaged account wrappers: one table, shared by asset
validation, FIRE math (services/fire.ACCESS_AGE) and the ladder, instead of
the access age living as a literal in services/fire.py and the OKI money
limits living nowhere at all.

Sources:
- https://www.munipro.pl/ustawa-oki-limity-podatek-zasady/
- https://inwestomat.eu/jak-ma-dzialac-osobiste-konto-inwestycyjne-oki/

OKI (Osobiste Konto Inwestycyjne) - statute signed 13 Aug 2026, accounts
open from 1 Jan 2027. Gains are exempt from Belka tax on up to 100 000 PLN
of assets held in the account (25 000 PLN of which may sit in the savings
sub-account); above the limit a flat annual charge applies to the excess
value, 0.85% for 2027. Limits are frozen until 2030. Unlike IKE/IKZE/PPK it
carries no age lock at all - money can be withdrawn any time - which is why
it is deliberately left out of ACCESS_AGE below.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WrapperInfo:
    key: str
    access_age: float | None  # None = no age lock (withdraw any time)
    available_from: int | None = None  # calendar year it can first be opened
    exempt_asset_limit: float | None = None  # OKI: Belka-exempt up to this much
    savings_sublimit: float | None = None  # OKI: of which this much may be the savings sub-account
    excess_rate_2027: float | None = None  # OKI: flat annual charge on value above the limit (2027)


WRAPPERS: dict[str, WrapperInfo] = {
    "ike": WrapperInfo(key="ike", access_age=60),
    "ikze": WrapperInfo(key="ikze", access_age=65),
    "ppk": WrapperInfo(key="ppk", access_age=60),
    "oipe": WrapperInfo(key="oipe", access_age=60),
    "oki": WrapperInfo(
        key="oki",
        access_age=None,
        available_from=2027,
        exempt_asset_limit=100_000,
        savings_sublimit=25_000,
        excess_rate_2027=0.0085,
    ),
}

# Age at which each wrapper's money becomes accessible without penalty.
# Wrappers with no age lock (currently only "oki") are absent from this dict
# on purpose, so `wrapper in ACCESS_AGE` doubles as "is this one locked".
ACCESS_AGE: dict[str, float] = {
    key: w.access_age for key, w in WRAPPERS.items() if w.access_age is not None
}
