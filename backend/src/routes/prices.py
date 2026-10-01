"""Price endpoints (metals, crypto, FX rates)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db
from ..services.price_service import PriceService, catalogue_payload
from .helpers import get_base_currency, held_symbols

router = APIRouter(prefix="/api/prices", tags=["prices"])


@router.get("")
def current_prices(db: Session = Depends(get_db)):
    """Prices for what the wallet actually holds, plus XAU/BTC/SOL for
    backward compatibility with the pre-existing `gold_per_gram` / `crypto`
    fields (which callers before this round already depend on)."""
    base = get_base_currency(db)
    ps = PriceService(base)
    held_metals, held_crypto = held_symbols(db)
    metals = {"XAU": round(ps.metal_price("XAU"), 4)}
    for sym in held_metals:
        metals.setdefault(sym, round(ps.metal_price(sym), 4))
    crypto = {u: round(ps.crypto_price(u), 2) for u in ({"BTC", "SOL"} | held_crypto)}
    return {
        "base_currency": base,
        "gold_per_gram": metals["XAU"],
        "metals": metals,
        "crypto": crypto,
        "fx": ps.rates(),
    }


@router.get("/catalogue")
def prices_catalogue():
    """The metals/crypto the app knows how to price: symbol, name (EN/PL),
    icon, default category/profile and pricing unit - what AssetForm on the
    frontend uses to fill in a new metal/crypto asset from a picked symbol."""
    return catalogue_payload()


@router.get("/gold")
def gold_price(db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {"base_currency": base, "per_gram": round(ps.gold_price(), 4)}


@router.get("/metal/{symbol}")
def metal_price(symbol: str, db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {
        "base_currency": base,
        "symbol": symbol.upper(),
        "per_gram": round(ps.metal_price(symbol.upper()), 4),
    }


@router.get("/crypto/{symbol}")
def crypto_price(symbol: str, db: Session = Depends(get_db)):
    base = get_base_currency(db)
    ps = PriceService(base)
    return {
        "base_currency": base,
        "symbol": symbol.upper(),
        "price": round(ps.crypto_price(symbol.upper()), 2),
    }
