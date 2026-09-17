"""Schema creation, migration and seeding - run as the *owning* role.

The application's runtime role deliberately holds no DDL rights, so none of
this can happen when the API starts. A Helm hook Job runs `python -m
src.schema` with the owner's client certificate before the new backend rolls
out; the app then connects with a role that can only read and write rows.

Safe to run repeatedly: every step checks before it acts.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import inspect, text

from .database import Base, engine
from .models import (  # noqa: F401 (import registers the tables on Base)
    asset,
    expense,
    monthly,
    position,
    settings as settings_model,
)
from .models.asset import Asset


def migrate() -> None:
    """Add columns that create_all() cannot introduce on an existing table.

    create_all only creates missing *tables*, so a column added to a model
    after the database exists stays absent until it is added here. Kept small
    on purpose - past a handful of columns this wants a real migration tool.
    """
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
        ("assets", "profile",
         "ALTER TABLE assets ADD COLUMN profile VARCHAR(12) NOT NULL DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS ix_assets_profile ON assets (profile)"),
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
        print(f"  + {table}.{column}")


def backfill_profiles() -> None:
    """Give every unclassified asset the band its class implies.

    Only touches rows that have no profile yet, so a deliberate per-asset
    override is never overwritten by a later run.
    """
    from .database import SessionLocal
    from .profiles import for_category

    db = SessionLocal()
    try:
        rows = db.query(Asset).filter((Asset.profile == "") | (Asset.profile.is_(None))).all()
        for a in rows:
            a.profile = for_category(a.category)
        if rows:
            db.commit()
            print(f"  + classified {len(rows)} asset(s) by risk profile")
    finally:
        db.close()


def seed() -> None:
    """Create the default asset types on a brand-new database."""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        if db.query(Asset).count():
            return
        db.add_all([
            Asset(name="Cash", kind="currency", category="Cash", profile="safe", icon="💵", units=""),
            Asset(name="Gold", kind="gold", category="Gold", profile="moderate", icon="🥇", units="g"),
            Asset(name="Stocks", kind="currency", category="Stocks", profile="risky", icon="📈", units=""),
            Asset(name="TFI Funds", kind="currency", category="TFI", profile="moderate", icon="🏦", units=""),
            Asset(name="National Bonds", kind="currency", category="Bonds", profile="safe", icon="📜", units=""),
            Asset(name="Watches", kind="currency", category="Watches", profile="illiquid", icon="⌚", units=""),
            Asset(name="Bitcoin", kind="crypto", category="Crypto", profile="risky", icon="₿", units="BTC"),
            Asset(name="Solana", kind="crypto", category="Crypto", profile="risky", icon="◎", units="SOL"),
            Asset(name="Savings", kind="currency", category="Savings", profile="safe", icon="🏧", units=""),
        ])
        db.commit()
        print("  + seeded default asset types")
    finally:
        db.close()


def grant_runtime_role(role: str) -> None:
    """Give the application role exactly what it needs and nothing more.

    Rows it may read and write; tables and schemas it may not create, drop or
    alter. Sequences are needed because the primary keys are generated.
    """
    if not role:
        return
    statements = [
        f'GRANT CONNECT ON DATABASE "{engine.url.database}" TO "{role}"',
        f'GRANT USAGE ON SCHEMA public TO "{role}"',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"',
        f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{role}"',
        # Anything this Job creates in future runs is covered without re-granting.
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
        f'GRANT USAGE, SELECT ON SEQUENCES TO "{role}"',
    ]
    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))
    print(f"  + granted read/write on public to {role}")


def main() -> int:
    url = str(engine.url)
    print(f"schema: {engine.url.drivername} -> {engine.url.database}")
    Base.metadata.create_all(bind=engine)
    migrate()
    seed()
    backfill_profiles()
    if engine.url.drivername.startswith("postgresql"):
        grant_runtime_role(os.environ.get("MYFINANCE_APP_ROLE", ""))
    print("schema: up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
