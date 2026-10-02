"""Wallet export / import: the file format, the plan, the round trip, isolation
and what a bad file does (nothing).

The round trip is the demo wallet (src.demo_seed) exported and imported into a
fresh second user, then every number the app derives from the setup compared
across the two. The demo seeder only runs on SQLite, so that test is skipped on
PostgreSQL; the rest build their data through the API and run on both.
"""
from __future__ import annotations

import json

import pytest

from src.config import settings as app_settings
from tests.conftest import make_user, session_for

ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}
ON_SQLITE = app_settings.database_url.startswith("sqlite")


def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _post_file(client, path: str, payload, *, raw: bytes | None = None):
    body = raw if raw is not None else json.dumps(payload).encode()
    return client.post(path, content=body, headers={"Content-Type": "application/json"})


def _wallet(**over) -> dict:
    base = {
        "format": "myfinance-wallet",
        "version": 1,
        "settings": {"base_currency": "PLN", "timezone": "Europe/Warsaw",
                     "features": ALL_ON},
        "assets": [],
        "income_sources": [],
        "expenses": [],
    }
    base.update(over)
    return base


CASH = {"name": "Cash", "kind": "currency", "category": "Cash", "profile": "safe",
        "icon": "x", "currency": "PLN", "amount": "1500.50", "value": "1500.5",
        "contributed": "1000"}


# --- the demo wallet, exported and imported ------------------------------------


def _numbers(s) -> dict:
    """What the app derives from a wallet's setup, for comparing two wallets."""
    from src.main import summary
    from src.routes import fire as fire_routes
    from src.routes import income as income_routes
    from src.routes import monthly as monthly_routes
    from src.routes.expenses import expense_summary
    from src.services.growth import portfolio_growth

    growth = portfolio_growth(s)
    from src.models.asset import Asset

    names = {a.id: a.name for a in s.query(Asset).all()}
    # "Your money" is `invested`; how it splits into an opening value and later
    # contributions is history, which a wallet file does not carry.
    per_asset = {names[a["asset_id"]]: (a["value"], a["invested"], a["growth"], a["growth_pct"])
                 for a in growth["assets"] if not a["archived"]}
    es = expense_summary(db=s)
    # Params are compared as the engine reads them (defaults filled in): a source
    # a seeder wrote with only some keys and its import mean the same thing.
    from src.schemas.income import PARAM_MODELS

    sources = {
        x.name: (x.current_month, PARAM_MODELS[x.kind].model_validate(x.params).model_dump())
        for x in income_routes.list_sources(db=s)
    }
    return {
        "summary": {k: v for k, v in summary(db=s).items()
                    if k in ("base_currency", "total_value", "positions")},
        "growth_total": {k: growth["total"][k] for k in ("value", "invested", "growth", "growth_pct")},
        "per_asset": per_asset,
        "expenses": (es.monthly_total, es.monthly_total_personal, es.active_count,
                     es.indefinite_count),
        "income": sources,
        "fire_settings": fire_routes._load_settings(s).model_dump(),
        # The FIRE projection starts from the portfolio value as it is today.
        "fire_start": fire_routes.get_fire(db=s)["result"]["projection"][0],
    }


@pytest.mark.skipif(not ON_SQLITE, reason="the demo seeder only runs on SQLite")
def test_demo_wallet_round_trip(db):
    from src import demo_seed
    from src.routes import monthly as monthly_routes
    from src.services import wallet_io
    from src.schemas.wallet import WalletFile

    # The seeder writes the fixed local user (the `db` fixture's user). It
    # leaves the fixture's features row alone.
    from src.services.users import default_assets

    db.add_all(default_assets(_local_id(db)))  # the fixture's user has none; a real one does
    db.commit()
    assert demo_seed.main() == 0
    source_exp = wallet_io.build_export(db, _local_id(db))
    # A real file: through JSON text and back.
    text = json.dumps(source_exp)
    wallet = WalletFile.model_validate(json.loads(text))

    bob = make_user("cd" * 32, provision=True)  # a new account: default asset types
    s2 = session_for(bob)
    try:
        plan = wallet_io.apply(s2, bob, wallet)
        assert plan.applied
        mine = _numbers(db)
        theirs = _numbers(s2)
        assert theirs["summary"] == mine["summary"]
        assert theirs["growth_total"] == mine["growth_total"]
        assert theirs["per_asset"] == mine["per_asset"]
        assert theirs["expenses"] == mine["expenses"]
        assert theirs["income"] == mine["income"]
        assert theirs["fire_settings"] == mine["fire_settings"]
        assert theirs["fire_start"]["value"] == mine["fire_start"]["value"]
        assert theirs["fire_start"]["age"] == mine["fire_start"]["age"]
        # What is *not* expected to match: figures read off the history that is not
        # exported (recorded spend, saved-per-month from flows) - FIRE's savings
        # rate, years-to-FI and the monthly spend it falls back from "recorded"
        # to "committed" on. Those restart as the new wallet accumulates history.
        # The budget side: committed spend for this month and the twelve ahead, and
        # this month's income net from the sources.
        a = monthly_routes.analytics(months_back=0, months_ahead=12, db=db)
        b = monthly_routes.analytics(months_back=0, months_ahead=12, db=s2)
        assert [p.committed for p in a.timeline] == [p.committed for p in b.timeline]
        assert a.timeline[0].committed > 0
        assert a.categories == b.categories
        # Income of the current month comes from the sources alone (no entry for
        # it in the demo, and entries are not exported).
        assert a.timeline[0].income == b.timeline[0].income
    finally:
        s2.close()


def _local_id(db):
    from src.identity import LOCAL_USER_ID

    return LOCAL_USER_ID
