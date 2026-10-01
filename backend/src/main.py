"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import auth_enabled, issuer, require_user, validate_config
from .config import settings
from .deps import get_db
from .models import (  # noqa: F401 (register models)
    asset,
    expense,
    income,
    insight,
    monthly,
    position,
    report,
    settings as settings_model,
    user,
)
from .routes import auth as auth_routes
from .routes import positions as positions_routes
from .routes import assets as assets_routes
from .routes import expenses as expenses_routes
from .routes import fire as fire_routes
from .routes import income as income_routes
from .routes import insights as insights_routes
from .routes import monthly as monthly_routes
from .routes import prices as prices_routes
from .routes import reports as reports_routes
from .routes import report_pdf as report_pdf_routes
from .routes import statistics as statistics_routes
from .routes import settings as settings_routes
from .routes import tax as tax_routes
from .services.price_service import PriceService
from .services import llm_queue


# NOTE: the schema is deliberately NOT created here. The runtime role has no
# DDL rights - see src/schema.py, which runs as the owning role from a Helm
# hook Job before the application starts.

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown.

    Startup: refuse an inconsistent authentication configuration, then clean up
    orphaned LLM jobs (pending/running/translating) left by a crash/restart of
    the previous instance.
    """
    validate_config()
    llm_queue.cleanup_interrupted_jobs()
    yield


app = FastAPI(title="MyFinance", version="1.0.0", lifespan=lifespan)

if not auth_enabled():
    # Loud on purpose. Leaving authentication unconfigured is the documented
    # way to run locally, but it is also what a half-finished deploy looks
    # like, and the consequence there is an API serving someone's finances to
    # anyone who can reach it. Everyone is then one fixed local user. (A
    # *partly* configured deploy never gets this far - validate_config() stops
    # it at startup.)
    log.warning(
        "AUTHENTICATION IS DISABLED - no OIDC issuer/audience (or Entra tenant/client) "
        "is configured. Every API endpoint is open, as one shared local user."
    )
else:
    log.info("OIDC authentication enabled for issuer %s", issuer())

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unauthenticated by design: /api/auth/config is what the browser reads before
# it has a token. /api/auth/me guards itself.
app.include_router(auth_routes.router)

# Everything that touches data is guarded here rather than endpoint by
# endpoint, so adding a router to this list is the only step needed and there
# is no decorator to forget.
protected = [
    positions_routes.router,
    assets_routes.router,
    expenses_routes.router,
    fire_routes.router,
    income_routes.router,
    insights_routes.router,
    monthly_routes.router,
    prices_routes.router,
    # Registered before reports_routes: that router's GET /{report_id}
    # would otherwise swallow /pdf as report_id="pdf" (Starlette matches
    # routes in registration order, and the two live under the same
    # /api/reports prefix - see routes/report_pdf.py).
    report_pdf_routes.router,
    reports_routes.router,
    statistics_routes.router,
    settings_routes.router,
    tax_routes.router,
]
for router in protected:
    app.include_router(router, dependencies=[Depends(require_user)])


# Left open deliberately: the kubelet's liveness and readiness probes call
# this and carry no credential. It reveals nothing beyond "the process is up".
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    """Convenience endpoint: current totals + live prices in one call."""
    from .models.asset import Asset
    from .models.settings import Setting
    from .routes.helpers import held_symbols, latest_positions_by_asset, value_of_position

    base = db.query(Setting).filter(Setting.key == "base_currency").first()
    base_currency = base.value if base else "PLN"
    assets = {a.id: a for a in db.query(Asset).all()}
    latest = latest_positions_by_asset(db)
    ps = PriceService(base_currency)
    gold_price = ps.gold_price()
    held_metals, held_crypto = held_symbols(db)
    # Only what the wallet holds (plus XAU/BTC/SOL for the pre-existing
    # gold_price / crypto_prices fields) - see routes/prices.py for why.
    metal_prices = {"XAU": round(gold_price, 4)}
    for sym in held_metals:
        metal_prices.setdefault(sym, round(ps.metal_price(sym), 4))
    crypto_prices = {u: ps.crypto_price(u) for u in ({"BTC", "SOL"} | held_crypto)}
    total = sum(
        value_of_position(db, assets[asset_id], p) for asset_id, p in latest.items()
    )
    return {
        "base_currency": base_currency,
        "total_value": round(total, 2),
        "positions": len(latest),
        "gold_price": gold_price,
        "crypto_prices": crypto_prices,
        "metals": metal_prices,
    }
