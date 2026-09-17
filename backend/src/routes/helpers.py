"""Shared helpers for position value calculation."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import DEFAULT_TIMEZONE, TIMEZONES
from ..timeutils import as_utc  # noqa: F401 (re-exported for routes)
from ..models.asset import Asset
from ..models.settings import Setting
from ..services.price_service import PriceService


def get_base_currency(db: Session) -> str:
    s = db.query(Setting).filter(Setting.key == "base_currency").first()
    return s.value if s else "PLN"


def get_timezone(db: Session) -> str:
    s = db.query(Setting).filter(Setting.key == "timezone").first()
    value = s.value if s else DEFAULT_TIMEZONE
    return value if value in TIMEZONES else DEFAULT_TIMEZONE


def today_in(db: Session) -> date:
    """Current date in the configured zone.

    Using the server's own date would roll an expense over to "ended" (or a new
    month over) at UTC midnight rather than the user's.
    """
    return datetime.now(ZoneInfo(get_timezone(db))).date()


def get_asset(db: Session, asset_id: int) -> Asset | None:
    return db.query(Asset).filter(Asset.id == asset_id).first()


def compute_value(
    db: Session, asset: Asset, amount: float, currency: str
) -> tuple[float, float, str]:
    """Return (value_in_base, price_used, base_currency) for a position.

    - currency asset: amount converted from `currency` to base.
    - gold: amount (grams) * gold price (base per gram).
    - crypto: amount (coin qty) * crypto price (base per coin).
    """
    base = get_base_currency(db)
    amount = float(amount)
    ps = PriceService(base)
    if asset.kind == "gold":
        price = ps.gold_price()
        value = amount * price
        return value, price, base
    if asset.kind == "crypto":
        price = ps.crypto_price(asset.units)
        value = amount * price
        return value, price, base
    # currency: convert amount -> USD -> base.
    # fx_rate(c) is units of `c` per 1 USD, so dividing by it gives USD.
    if currency == base:
        return amount, 1.0, base
    rate = float(ps.fx_rate(base)) / float(ps.fx_rate(currency))
    value = amount * rate
    return value, rate, base


def convert_currency(ps: PriceService, amount: float, currency: str, base: str) -> float:
    """Convert `amount` from `currency` into `base`, routed via USD."""
    if currency == base:
        return float(amount)
    return float(amount) * (ps.fx_rate(base) / ps.fx_rate(currency))


def latest_positions_by_asset(db: Session) -> dict[int, "Position"]:
    """Map asset_id -> its most recent position row."""
    from ..models.position import Position

    rows = (
        db.query(Position)
        .order_by(Position.asset_id, Position.timestamp.desc(), Position.id.desc())
        .all()
    )
    latest: dict[int, "Position"] = {}
    for r in rows:
        if r.asset_id not in latest:
            latest[r.asset_id] = r
    return latest


def value_of_position(db: Session, asset: Asset, p: "Position") -> float:
    """Current base-currency value of a position row (live prices)."""
    value, _, _ = compute_value(db, asset, p.amount, p.currency)
    return float(value)
