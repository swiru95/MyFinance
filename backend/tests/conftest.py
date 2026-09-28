"""Test harness: a throwaway SQLite database and no network.

The engine in src/database.py is built from settings at import time, so the
URL has to be in the environment before anything under src is imported -
which is why it is set at module level rather than inside a fixture.
"""
import os
import tempfile
from datetime import date

_TMP = tempfile.mkdtemp(prefix="myfinance-tests-")
os.environ["MYFINANCE_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["MYFINANCE_DATA_DIR"] = _TMP
# Never inherit a real tenant or model server from the developer's shell.
for _var in ("MYFINANCE_AUTH_TENANT_ID", "MYFINANCE_AUTH_CLIENT_ID",
             "MYFINANCE_LLM_BASE_URL", "MYFINANCE_LLM_API_KEY"):
    os.environ.pop(_var, None)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def offline_prices(monkeypatch):
    """Serve every price from the static fallbacks.

    Tests must not depend on gold-api, CoinGecko or open.er-api being up, and
    fixed prices make expected values exact.
    """
    from src.services import price_service as ps

    ps._CACHE.clear()
    ps._NBP_CACHE.clear()
    monkeypatch.setattr(
        ps.PriceService, "_fetch_fx",
        lambda self, c: (ps._FALLBACK_FX.get(c, 1.0), True),
    )
    monkeypatch.setattr(
        ps.PriceService, "_fetch_metal_usd_per_oz",
        lambda self, s: (ps._FALLBACK_METAL_USD_PER_OZ.get(s.upper(), 0.0), True),
    )
    monkeypatch.setattr(
        ps.PriceService, "_fetch_crypto_usd",
        lambda self, s: (ps._FALLBACK_CRYPTO_USD.get(s.upper(), 0.0), True),
    )
    monkeypatch.setattr(
        ps.PriceService, "nbp_reference_rate",
        lambda self: (date(2026, 3, 5), 3.75),
    )


@pytest.fixture
def db():
    """A fresh schema per test, dropped afterwards.

    Advanced features start all-on here (unlike a real new database, which
    schema.seed_features() leaves all-off) - almost every test in this suite
    predates feature toggles and exercises portfolio/FIRE/tax/insights
    behaviour without ever touching Settings, so defaulting the test harness
    to "everything on" (the same state schema.seed_features() gives an
    upgrading, already-populated database) keeps them meaningful. Tests of
    the toggles themselves (test_settings.py, the off-branches in
    test_ladder.py) turn features off explicitly through the API.
    """
    import json

    from src import schema  # noqa: F401  (registers every model on Base)
    from src.database import Base, SessionLocal, engine
    from src.models.settings import Setting

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    session.add(Setting(
        key="features",
        value=json.dumps({"portfolio": True, "fire": True, "tax": True, "insights": True}),
    ))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """The real app over the per-test database, authentication off."""
    from fastapi.testclient import TestClient

    from src.main import app

    with TestClient(app) as c:
        yield c
