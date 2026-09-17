"""Price endpoints (gold, crypto, FX rates)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..services.price_service import PriceService
from .helpers import get_base_currency

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("")
def current_prices(db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {
        "base_currency": base,
        "gold_per_gram": round(ps.gold_price(), 4),
        "crypto": {u: round(ps.crypto_price(u), 2) for u in ("BTC", "SOL")},
        "fx": ps.rates(),
    }


@router.get("/gold")
def gold_price(db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {"base_currency": base, "per_gram": round(ps.gold_price(), 4)}


@router.get("/crypto/{symbol}")
def crypto_price(symbol: str, db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {
        "base_currency": base,
        "symbol": symbol.upper(),
        "price": round(ps.crypto_price(symbol.upper()), 2),
    }
