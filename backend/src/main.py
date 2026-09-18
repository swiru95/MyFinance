"""FastAPI application entry point."""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import auth_enabled, require_user
from .config import settings
from .models import (  # noqa: F401 (register models)
    asset,
    expense,
    monthly,
    position,
    report,
    settings as settings_model,
)
from .routes import auth as auth_routes
from .routes import positions as positions_routes
from .routes import assets as assets_routes
from .routes import expenses as expenses_routes
from .routes import monthly as monthly_routes
from .routes import prices as prices_routes
from .routes import reports as reports_routes
from .routes import statistics as statistics_routes
from .routes import settings as settings_routes
from .services.price_service import PriceService


# NOTE: the schema is deliberately NOT created here. The runtime role has no
# DDL rights - see src/schema.py, which runs as the owning role from a Helm
# hook Job before the application starts.

log = logging.getLogger(__name__)

app = FastAPI(title="MyFinance", version="1.0.0")

if not auth_enabled():
    # Loud on purpose. Leaving the tenant unset is the documented way to run
    # locally, but it is also what a half-finished deploy looks like, and the
    # consequence there is an API serving someone's finances to anyone who can
    # reach it. The only signal is this line.
    log.warning(
        "AUTHENTICATION IS DISABLED - MYFINANCE_AUTH_TENANT_ID and "
        "MYFINANCE_AUTH_CLIENT_ID are not both set. Every API endpoint is open."
    )
else:
    log.info(
        "Entra ID authentication enabled for tenant %s, client %s",
        settings.auth_tenant_id,
        settings.auth_client_id,
    )

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
    monthly_routes.router,
    prices_routes.router,
    reports_routes.router,
    statistics_routes.router,
    settings_routes.router,
]
for router in protected:
    app.include_router(router, dependencies=[Depends(require_user)])


# Left open deliberately: the kubelet's liveness and readiness probes call
# this and carry no credential. It reveals nothing beyond "the process is up".
@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary", dependencies=[Depends(require_user)])
def summary() -> dict:
    """Convenience endpoint: current totals + live prices in one call."""
    from .database import SessionLocal
    from .models.asset import Asset
    from .models.settings import Setting
    from .routes.helpers import latest_positions_by_asset, value_of_position

    db = SessionLocal()
    try:
        base = db.query(Setting).filter(Setting.key == "base_currency").first()
        base_currency = base.value if base else "PLN"
        assets = {a.id: a for a in db.query(Asset).all()}
        latest = latest_positions_by_asset(db)
        ps = PriceService(base_currency)
        gold_price = ps.gold_price()
        crypto_prices = {u: ps.crypto_price(u) for u in ("BTC", "SOL")}
        total = sum(
            value_of_position(db, assets[asset_id], p) for asset_id, p in latest.items()
        )
        return {
            "base_currency": base_currency,
            "total_value": round(total, 2),
            "positions": len(latest),
            "gold_price": gold_price,
            "crypto_prices": crypto_prices,
        }
    finally:
        db.close()
