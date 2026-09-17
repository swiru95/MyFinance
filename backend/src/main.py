"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .models import (  # noqa: F401 (register models)
    asset,
    expense,
    monthly,
    position,
    settings as settings_model,
)
from .routes import positions as positions_routes
from .routes import assets as assets_routes
from .routes import expenses as expenses_routes
from .routes import monthly as monthly_routes
from .routes import prices as prices_routes
from .routes import statistics as statistics_routes
from .routes import settings as settings_routes
from .services.price_service import PriceService


Base.metadata.create_all(bind=engine)


def _migrate() -> None:
    """Add columns that create_all() cannot introduce on an existing table.

    SQLAlchemy's create_all only creates missing *tables*, so a column added to
    a model after a database already exists is silently absent until it is added
    here. Kept deliberately small - if this grows past a handful of columns it
    should become a real migration tool.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    # (table, column, DDL to add it, optional index DDL)
    wanted = [
        ("assets", "category",
         "ALTER TABLE assets ADD COLUMN category VARCHAR(60) NOT NULL DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS ix_assets_category ON assets (category)"),
        ("assets", "interest_basis",
         "ALTER TABLE assets ADD COLUMN interest_basis VARCHAR(10) NOT NULL DEFAULT ''",
         None),
        ("positions", "accrues_from",
         "ALTER TABLE positions ADD COLUMN accrues_from DATE",
         None),
    ]
    for table, column, add_sql, index_sql in wanted:
        if table not in tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(add_sql))
            if index_sql:
                conn.execute(text(index_sql))


_migrate()


def _seed() -> None:
    """Create default asset types on first start."""
    from .database import SessionLocal
    from .models.asset import Asset

    db = SessionLocal()
    try:
        if db.query(Asset).count() == 0:
            defaults = [
                Asset(name="Cash", kind="currency", category="Cash", icon="💵", units=""),
                Asset(name="Gold", kind="gold", category="Gold", icon="🥇", units="g"),
                Asset(name="Stocks", kind="currency", category="Stocks", icon="📈", units=""),
                Asset(name="TFI Funds", kind="currency", category="TFI", icon="🏦", units=""),
                Asset(name="National Bonds", kind="currency", category="Bonds", icon="📜", units=""),
                Asset(name="Watches", kind="currency", category="Watches", icon="⌚", units=""),
                Asset(name="Bitcoin", kind="crypto", category="Crypto", icon="₿", units="BTC"),
                Asset(name="Solana", kind="crypto", category="Crypto", icon="◎", units="SOL"),
                Asset(name="Savings", kind="currency", category="Savings", icon="🏧", units=""),
            ]
            db.add_all(defaults)
            db.commit()
    finally:
        db.close()


_seed()

app = FastAPI(title="MyFinance", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(positions_routes.router)
app.include_router(assets_routes.router)
app.include_router(expenses_routes.router)
app.include_router(monthly_routes.router)
app.include_router(prices_routes.router)
app.include_router(statistics_routes.router)
app.include_router(settings_routes.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
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
