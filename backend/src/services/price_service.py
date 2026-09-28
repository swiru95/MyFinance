"""Fetches live prices: metals (per gram), crypto (per coin), FX rates.

Everything is fetched in USD first, then converted to the base currency using
the FX table. A static fallback is used when the network/APIs are unavailable
so the app keeps working offline.

Also holds the one catalogue of metals/crypto the app knows how to price
(CATALOGUE below), so the supported symbol list, its display names/icons and
its default category/profile live in exactly one place instead of drifting
across routes, schemas and demo data.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import httpx

# Fallback values (used when external APIs are unreachable), USD per troy
# ounce. Approximate, offline fallbacks - dated so it is obvious how stale
# they are. XAU is the pre-existing value, kept as-is for continuity.
_FALLBACK_METAL_USD_PER_OZ = {
    "XAU": 2650.0,
    "XAG": 31.0,  # silver, offline fallback ~2026-09
    "XPT": 1000.0,  # platinum, offline fallback ~2026-09
    "XPD": 1000.0,  # palladium, offline fallback ~2026-09
}
# Stablecoins are deliberately excluded from the crypto catalogue: pegged to
# a fiat currency, they are a cash position, not an investment, so listing
# one here would double-count it against the "currency" kind that already
# covers cash. Offline fallbacks, USD per coin, ~2026-09.
_FALLBACK_CRYPTO_USD = {"BTC": 65000.0, "SOL": 150.0, "ETH": 3500.0, "XRP": 0.6, "BNB": 600.0}
# 1 USD -> these currencies (approximate, offline fallback).
_FALLBACK_FX = {"USD": 1.0, "EUR": 0.92, "PLN": 3.95, "CHF": 0.88}

_OZ_TO_GRAM = 31.1034768

# CoinGecko ids for the coins in the catalogue below - looked up once here
# rather than re-derived at every call site.
_CRYPTO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "BNB": "binancecoin",
}


@dataclass(frozen=True)
class CatalogueEntry:
    symbol: str
    kind: str  # "metal" | "crypto"
    name_en: str
    name_pl: str
    icon: str
    category: str
    profile: str
    unit: str  # "g" (metals, priced per gram) | "coin" (crypto, priced per unit)

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "kind": self.kind,
            "name": {"en": self.name_en, "pl": self.name_pl},
            "icon": self.icon,
            "category": self.category,
            "profile": self.profile,
            "unit": self.unit,
        }


# The one place the app's supported metals/crypto are listed: symbol, name in
# both languages, icon, default category/profile and pricing unit. AssetForm
# on the frontend fills name/icon/category/profile/units from this via
# GET /api/prices/catalogue; compute_value prices by symbol.
#
# Gold (XAU) keeps category "Gold" for backward compatibility with the
# pre-existing kind="gold" assets; the other three metals default to
# "Metals" (see profiles.BY_CATEGORY / services/returns.CATEGORY_RETURNS -
# same moderate band and return as Gold).
METALS_CATALOGUE: tuple[CatalogueEntry, ...] = (
    CatalogueEntry("XAU", "metal", "Gold", "Złoto", "🥇", "Gold", "moderate", "g"),
    CatalogueEntry("XAG", "metal", "Silver", "Srebro", "🥈", "Metals", "moderate", "g"),
    CatalogueEntry("XPT", "metal", "Platinum", "Platyna", "⬜", "Metals", "moderate", "g"),
    CatalogueEntry("XPD", "metal", "Palladium", "Pallad", "⬛", "Metals", "moderate", "g"),
)
CRYPTO_CATALOGUE: tuple[CatalogueEntry, ...] = (
    CatalogueEntry("BTC", "crypto", "Bitcoin", "Bitcoin", "₿", "Crypto", "risky", "coin"),
    CatalogueEntry("ETH", "crypto", "Ethereum", "Ethereum", "Ξ", "Crypto", "risky", "coin"),
    CatalogueEntry("SOL", "crypto", "Solana", "Solana", "◎", "Crypto", "risky", "coin"),
    CatalogueEntry("XRP", "crypto", "XRP", "XRP", "✕", "Crypto", "risky", "coin"),
    CatalogueEntry("BNB", "crypto", "BNB", "BNB", "🔶", "Crypto", "risky", "coin"),
)
CATALOGUE: tuple[CatalogueEntry, ...] = METALS_CATALOGUE + CRYPTO_CATALOGUE

METAL_SYMBOLS = frozenset(e.symbol for e in METALS_CATALOGUE)
CRYPTO_SYMBOLS = frozenset(e.symbol for e in CRYPTO_CATALOGUE)


def catalogue_payload() -> dict:
    """Serialised catalogue for GET /api/prices/catalogue."""
    return {
        "metals": [e.as_dict() for e in METALS_CATALOGUE],
        "crypto": [e.as_dict() for e in CRYPTO_CATALOGUE],
    }

# NBP publishes the current policy rates as XML. There is no API for the
# *historical* series (api.nbp.pl covers FX and gold only), so the past lives in
# services/interest.py and only today's rate is fetched.
_NBP_RATES_URL = "https://static.nbp.pl/dane/stopy/stopy_procentowe.xml"
# Last value known at authoring time; used when NBP is unreachable.
_FALLBACK_NBP_REF = (2026, 3, 5, 3.75)
_NBP_CACHE: dict[str, tuple[tuple, float]] = {}

# Cache shared across PriceService instances *and* requests. Each request used
# to build its own instance, so the per-instance cache never survived a call and
# every position re-hit the upstream APIs - which gets you rate-limited (HTTP
# 429) within minutes. Values cached here are raw USD / FX figures, which are
# base-currency independent, so switching base currency does not invalidate them.
_CACHE: dict[str, tuple[float, float]] = {}
_CACHE_LOCK = threading.Lock()
# After a failed fetch, wait this long before trying upstream again instead of
# hammering an API that is already refusing us.
_FAILURE_COOLDOWN = 60.0


class PriceService:
    def __init__(self, base_currency: str = "PLN", cache_ttl: int = 300):
        self.base_currency = base_currency
        self.cache_ttl = cache_ttl

    # ------------------------------------------------------------------ cache
    def _get_cached(self, key: str) -> float | None:
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
        if entry and (time.time() - entry[1]) < self.cache_ttl:
            return entry[0]
        return None

    def _set_cached(self, key: str, value: float, ttl: float | None = None) -> None:
        """Store `value`. A shorter `ttl` is used to back off after a failure."""
        ts = time.time()
        if ttl is not None:
            # Backdate the entry so it expires after `ttl` rather than cache_ttl.
            ts -= max(0.0, self.cache_ttl - ttl)
        with _CACHE_LOCK:
            _CACHE[key] = (value, ts)

    # --------------------------------------------------------------------- fx
    def fx_rate(self, currency: str) -> float:
        """Units of `currency` per 1 USD."""
        if currency == "USD":
            return 1.0
        key = f"fx_{currency}"
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        rate, ok = self._fetch_fx(currency)
        self._set_cached(key, rate, None if ok else _FAILURE_COOLDOWN)
        return rate

    def _fetch_fx(self, currency: str) -> tuple[float, bool]:
        """Return (units_per_usd, fetched_successfully)."""
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    "https://open.er-api.com/v6/latest/USD",
                    headers={"User-Agent": "myfinance/1.0"},
                )
                r.raise_for_status()
                data = r.json()
                return float(data["rates"][currency]), True
        except Exception:
            return _FALLBACK_FX.get(currency, 1.0), False

    def to_base(self, amount_usd: float) -> float:
        """Convert a USD amount to the base currency."""
        if self.base_currency == "USD":
            return amount_usd
        return amount_usd * self.fx_rate(self.base_currency)

    # ------------------------------------------------------------------ metal
    def metal_price(self, symbol: str) -> float:
        """`symbol` (XAU/XAG/XPT/XPD) price in base currency per gram."""
        symbol = symbol.upper()
        key = f"metal_usd_per_oz_{symbol}"
        usd_per_oz = self._get_cached(key)
        if usd_per_oz is None:
            usd_per_oz, ok = self._fetch_metal_usd_per_oz(symbol)
            self._set_cached(key, usd_per_oz, None if ok else _FAILURE_COOLDOWN)
        return self.to_base(usd_per_oz / _OZ_TO_GRAM)

    def gold_price(self) -> float:
        """Backward-compat alias: kind="gold" assets are always XAU."""
        return self.metal_price("XAU")

    def _fetch_metal_usd_per_oz(self, symbol: str) -> tuple[float, bool]:
        """Return (usd_per_oz, fetched_successfully).

        gold-api.com is keyless and, verified by hand (2026-09-27), answers
        XAU/XAG/XPT/XPD alike - so the same call shape covers all four
        metals, not just gold.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    f"https://api.gold-api.com/price/{symbol}",
                    headers={"User-Agent": "myfinance/1.0"},
                )
                r.raise_for_status()
                data = r.json()
                # gold-api returns {"price": <usd per oz>, ...}
                price = data.get("price")
                if price:
                    return float(price), True
        except Exception:
            pass
        return _FALLBACK_METAL_USD_PER_OZ.get(symbol, 0.0), False

    # ----------------------------------------------------------------- crypto
    def crypto_price(self, symbol: str) -> float:
        """Price of one coin in base currency."""
        symbol = symbol.upper()
        key = f"crypto_usd_{symbol}"
        usd = self._get_cached(key)
        if usd is None:
            usd, ok = self._fetch_crypto_usd(symbol)
            self._set_cached(key, usd, None if ok else _FAILURE_COOLDOWN)
        return self.to_base(usd)

    def _fetch_crypto_usd(self, symbol: str) -> tuple[float, bool]:
        """Return (usd_price, fetched_successfully) for `symbol`.

        One CoinGecko call prices every coin in the catalogue at once (rather
        than one call per coin) and caches each result as a side effect, so a
        wallet holding several coins costs one request, not several - and
        stays under CoinGecko's rate limit instead of tripping the 429s the
        old per-coin version used to hit.
        """
        if symbol not in _CRYPTO_IDS:
            return _FALLBACK_CRYPTO_USD.get(symbol, 0.0), False
        ids = ",".join(_CRYPTO_IDS.values())
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd",
                    headers={"User-Agent": "myfinance/1.0"},
                )
                r.raise_for_status()
                data = r.json()
                result: float | None = None
                for sym, coin_id in _CRYPTO_IDS.items():
                    if coin_id in data and "usd" in data[coin_id]:
                        price = float(data[coin_id]["usd"])
                        if sym == symbol:
                            result = price
                        else:
                            # Piggyback: cache the other coins from this same
                            # response so requesting them next costs nothing.
                            self._set_cached(f"crypto_usd_{sym}", price)
                if result is not None:
                    return result, True
        except Exception:
            pass
        return _FALLBACK_CRYPTO_USD.get(symbol, 0.0), False

    # ------------------------------------------------------------- convenience
    def nbp_reference_rate(self) -> tuple["date", float]:
        """Current NBP reference rate as (in force from, percent).

        Cached for a day: the rate changes at most once a month, after an RPP
        meeting, so polling it per request would be pointless traffic.
        """
        from datetime import date as _date
        import xml.etree.ElementTree as ET

        entry = _NBP_CACHE.get("ref")
        if entry and (time.time() - entry[1]) < 86400:
            return entry[0]

        y, m, d, pct = _FALLBACK_NBP_REF
        value = (_date(y, m, d), pct)
        try:
            resp = httpx.get(_NBP_RATES_URL, timeout=10)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for pos in root.iter("pozycja"):
                if pos.get("id") == "ref":
                    # NBP writes decimals with a comma.
                    rate = float(pos.get("oprocentowanie", "").replace(",", "."))
                    when = _date.fromisoformat(pos.get("obowiazuje_od", ""))
                    value = (when, rate)
                    break
        except Exception:
            pass
        _NBP_CACHE["ref"] = (value, time.time())
        return value

    def rates(self) -> dict[str, float]:
        """1 USD in each currency (base-aware)."""
        return {c: self.fx_rate(c) for c in ("EUR", "PLN", "CHF", "USD")}
