"""Test harness: a throwaway SQLite database and no network.

The engine in src/database.py is built from settings at import time, so the
URL has to be in the environment before anything under src is imported -
which is why it is set at module level rather than inside a fixture.
"""
import os
import tempfile
from datetime import date

_TMP = tempfile.mkdtemp(prefix="myfinance-tests-")
# Defaults to a throwaway SQLite file. Point MYFINANCE_TEST_DATABASE_URL at a
# scratch PostgreSQL database to run the suite there instead (tables are
# created and dropped per test, so use an empty database, never a real one).
os.environ["MYFINANCE_DATABASE_URL"] = os.environ.get(
    "MYFINANCE_TEST_DATABASE_URL", f"sqlite:///{_TMP}/test.db"
)
os.environ["MYFINANCE_DATA_DIR"] = _TMP
# Never inherit a real tenant or model server from the developer's shell.
for _var in ("MYFINANCE_AUTH_TENANT_ID", "MYFINANCE_AUTH_CLIENT_ID",
             "MYFINANCE_AUTH_ISSUER", "MYFINANCE_AUTH_AUDIENCE",
             "MYFINANCE_AUTH_API_SCOPE", "MYFINANCE_AUTH_REQUIRED_ROLE",
             "MYFINANCE_SUBJECT_PEPPER", "MYFINANCE_BOOTSTRAP_ISS",
             "MYFINANCE_BOOTSTRAP_SUB",
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
    from src.database import Base, engine
    from src.models.settings import Setting
    from src.scoping import open_session
    from src.services.users import get_or_create_local_user

    Base.metadata.create_all(bind=engine)
    # The session is the fixed local user's, which is who the `client` fixture
    # (authentication off) is served as - so rows a test adds here are the rows
    # its API calls see. No default asset types: these tests start empty.
    session = open_session(get_or_create_local_user(provision=False))
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


# --- Authentication on, against a fake OIDC issuer ---------------------------

@pytest.fixture
def idp(monkeypatch, db):
    """Authentication enabled for a generic OIDC issuer, served by FakeIdP.

    Settings are patched on the live `settings` object (the module reads them
    per request), and the only network call - `auth._fetch_json`, used for
    both the discovery document and the JWKS - is replaced. Everything else,
    signature, claim and user-row handling, is the real code.
    """
    from src import auth
    from src.config import settings
    from tests.fake_oidc import AUDIENCE, ISSUER, PEPPER, FakeIdP

    fake = FakeIdP()
    for name, value in (
        ("auth_issuer", ISSUER),
        ("auth_audience", AUDIENCE),
        ("auth_client_id", ""),
        ("auth_tenant_id", ""),
        ("auth_api_scope", None),
        ("auth_required_role", None),
        ("subject_pepper", PEPPER),
    ):
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(auth, "_fetch_json", fake.fetch)
    auth.reset_key_cache()
    yield fake
    auth.reset_key_cache()


def make_client(token: str | None = None):
    """A TestClient that sends `token` as a bearer credential."""
    from fastapi.testclient import TestClient

    from src.main import app

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return TestClient(app, headers=headers)


@pytest.fixture
def two_users(idp):
    """(alice, bob): two signed-in clients on the same database."""
    alice = make_client(idp.token("sub-alice", name="Alice Example", email="alice@example.test"))
    bob = make_client(idp.token("sub-bob", name="Bob Example", email="bob@example.test"))
    return alice, bob
