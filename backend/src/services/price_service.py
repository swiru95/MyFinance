"""Fetches live prices: gold (per gram), crypto (per coin), FX rates.

Everything is fetched in USD first, then converted to the base currency using
the FX table. A static fallback is used when the network/APIs are unavailable
so the app keeps working offline.
"""
from __future__ import annotations

import threading
import time
import httpx

# Fallback values (used when external APIs are unreachable).
_FALLBACK_GOLD_USD_PER_OZ = 2650.0
_FALLBACK_CRYPTO_USD = {"BTC": 65000.0, "SOL": 150.0}
# 1 USD -> these currencies (approximate, offline fallback).
_FALLBACK_FX = {"USD": 1.0, "EUR": 0.92, "PLN": 3.95, "CHF": 0.88}

_OZ_TO_GRAM = 31.1034768

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

    # ------------------------------------------------------------------- gold
    def gold_price(self) -> float:
        """Gold price in base currency per gram."""
        usd_per_oz = self._get_cached("gold_usd_per_oz")
        if usd_per_oz is None:
            usd_per_oz, ok = self._fetch_gold_usd_per_oz()
            self._set_cached(
                "gold_usd_per_oz", usd_per_oz, None if ok else _FAILURE_COOLDOWN
            )
        return self.to_base(usd_per_oz / _OZ_TO_GRAM)

    def _fetch_gold_usd_per_oz(self) -> tuple[float, bool]:
        """Return (usd_per_oz, fetched_successfully)."""
        # GoldAPI.io free tier requires a key; try a keyless public endpoint
        # first, then fall back to a static price.
        candidates = [
            "https://api.gold-api.com/price/XAU",
        ]
        for url in candidates:
            try:
                with httpx.Client(timeout=5.0) as client:
                    r = client.get(url, headers={"User-Agent": "myfinance/1.0"})
                    r.raise_for_status()
                    data = r.json()
                    # gold-api returns {"price": <usd per oz>, ...}
                    price = data.get("price")
                    if price:
                        return float(price), True
            except Exception:
                continue
        return _FALLBACK_GOLD_USD_PER_OZ, False

    # ----------------------------------------------------------------- crypto
    def crypto_price(self, symbol: str) -> float:
        """Price of one coin in base currency."""
        key = f"crypto_usd_{symbol.upper()}"
        usd = self._get_cached(key)
        if usd is None:
            usd, ok = self._fetch_crypto_usd(symbol)
            self._set_cached(key, usd, None if ok else _FAILURE_COOLDOWN)
        return self.to_base(usd)

    def _fetch_crypto_usd(self, symbol: str) -> tuple[float, bool]:
        """Return (usd_price, fetched_successfully)."""
        coin = {"BTC": "bitcoin", "SOL": "solana"}.get(symbol.upper())
        if not coin:
            return _FALLBACK_CRYPTO_USD.get(symbol.upper(), 0.0), False
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd",
                    headers={"User-Agent": "myfinance/1.0"},
                )
                r.raise_for_status()
                data = r.json()
                if coin in data and "usd" in data[coin]:
                    return float(data[coin]["usd"]), True
        except Exception:
            pass
        return _FALLBACK_CRYPTO_USD.get(symbol.upper(), 0.0), False

    # ------------------------------------------------------------- convenience
    def rates(self) -> dict[str, float]:
        """1 USD in each currency (base-aware)."""
        return {c: self.fx_rate(c) for c in ("EUR", "PLN", "CHF", "USD")}
