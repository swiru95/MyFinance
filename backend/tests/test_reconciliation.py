"""The PDF report's reconciliation identity, checked against the real demo
database - not a synthetic fixture - because that is what the PDF review
that prompted this test actually opened. Runs `python -m src.demo_seed`
against a throwaway SQLite file in its own subprocess (the same command the
task's own instructions use to make a demo DB), then opens that database
directly to check, for every reporting period:

    opening_value + contributed + growth == value      (reconciles)
    value == /api/statistics/allocation's total          (matches the headline)

to the grosz (exact equality on the rounded, displayed figures - not
pytest.approx), for all five periods efficiency.PERIODS offers.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    """A real demo database, seeded exactly as the README/task instructions
    describe: `python -m src.demo_seed` into an empty SQLite dir. Built once
    per test module (seeding takes a moment and every test below only
    reads)."""
    data_dir = tmp_path_factory.mktemp("demo_reconciliation")
    db_url = f"sqlite:///{data_dir}/myfinance.db"
    env = dict(os.environ)
    env["MYFINANCE_DATA_DIR"] = str(data_dir)
    env["MYFINANCE_DATABASE_URL"] = db_url
    for var in (
        "MYFINANCE_AUTH_TENANT_ID", "MYFINANCE_AUTH_CLIENT_ID",
        "MYFINANCE_LLM_BASE_URL", "MYFINANCE_LLM_API_KEY",
    ):
        env.pop(var, None)

    result = subprocess.run(
        [sys.executable, "-m", "src.demo_seed"],
        cwd=str(_BACKEND_DIR), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"demo_seed failed:\n{result.stdout}\n{result.stderr}"

    from sqlalchemy import select

    from src.crypto.core import LOCAL_SECRET, KeyRing, active_keks, unwrap_dek
    from src.database import KEYRING_KEY, KeyedSession
    from src.identity import LOCAL_USER_ID
    from src.models.user import User

    engine = create_engine(db_url)
    # The demo wallet is the fixed local user's (what the app serves with
    # authentication off), so this session is confined to that user - and holds
    # their key, unwrapped the way a request would: the demo database's values
    # are stored encrypted.
    with engine.connect() as conn:
        salt, wrapped, version = conn.execute(
            select(User.key_salt, User.wrapped_dek, User.kek_version).where(User.id == LOCAL_USER_ID)
        ).one()
    keks = active_keks()
    dek = unwrap_dek(
        wrapped, user_id=LOCAL_USER_ID, kek=keks.get(version), kek_version=version,
        salt=salt, secret=LOCAL_SECRET,
    )
    session_factory = sessionmaker(
        bind=engine, class_=KeyedSession,
        info={"user_id": LOCAL_USER_ID, KEYRING_KEY: KeyRing(LOCAL_USER_ID, dek)},
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_reconciliation_and_headline_match_for_every_period(demo_db):
    from src.routes.helpers import today_in
    from src.routes.statistics import allocation as allocation_route
    from src.services.efficiency import PERIODS, period_efficiency

    db = demo_db
    today = today_in(db)
    alloc = allocation_route(db=db)

    for period in PERIODS:
        eff = period_efficiency(db, period, today)
        total = eff["total"]

        reconciled = round(total["opening_value"] + total["contributed"] + total["growth"], 2)
        assert reconciled == total["value"], (
            f"{period}: opening({total['opening_value']}) + "
            f"contributed({total['contributed']}) + growth({total['growth']}) "
            f"= {reconciled}, does not equal value ({total['value']})"
        )

        assert total["value"] == alloc["total"], (
            f"{period}: total.value ({total['value']}) does not match "
            f"the allocation endpoint's headline total ({alloc['total']})"
        )
