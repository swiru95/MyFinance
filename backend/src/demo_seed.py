"""Demo data seeder for an empty SQLite database.

Creates a complete fictional portfolio and income history for testing and demo
purposes. Refuses to run unless: (1) database is SQLite, (2) database is empty
(no existing positions, expenses, monthly records, income sources).

Run as: MYFINANCE_DATA_DIR=<dir> python -m src.demo_seed
"""

import json
import sys
import os
from datetime import datetime, date, timezone as tz, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, engine, SessionLocal
from .schema import backfill_profiles, migrate, seed, seed_features
from .models.asset import Asset
from .models.expense import Expense
from .models.monthly import MonthlyRecord
from .models.position import Position
from .models.income import IncomeSource, IncomeEntry
from .models.settings import Setting


def _check_safety() -> None:
    """Refuse unless database is SQLite."""
    url_str = str(settings.database_url)
    if not url_str.startswith("sqlite:"):
        print(f"ERROR: Not a SQLite database: {url_str}", file=sys.stderr)
        sys.exit(2)


def _check_empty(db: Session) -> None:
    """Check if database is empty (no existing data)."""
    # Check if database has any existing data
    has_positions = db.query(Position).count() > 0
    has_expenses = db.query(Expense).count() > 0
    has_monthly = db.query(MonthlyRecord).count() > 0
    has_income = db.query(IncomeSource).count() > 0

    if has_positions or has_expenses or has_monthly or has_income:
        print(
            "ERROR: Database is not empty. Demo seeder only fills empty databases.",
            file=sys.stderr,
        )
        sys.exit(2)


def _now_warsaw() -> datetime:
    """Get current time in Warsaw timezone."""
    return datetime.now(ZoneInfo("Europe/Warsaw"))


def _month_key(dt: datetime | date) -> str:
    """Format date as 'YYYY-MM'."""
    if isinstance(dt, datetime):
        dt = dt.date()
    return dt.strftime("%Y-%m")


def _months_range(start: date, end: date) -> list[str]:
    """List all 'YYYY-MM' strings from start to end inclusive."""
    result = []
    current = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    while current <= end_month:
        result.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return result


def _add_months(d: date, n: int) -> date:
    """Add n months to a date."""
    month = d.month - 1 + n
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _create_extra_assets(db: Session) -> dict[str, Asset]:
    """Create the three extra asset types for retirement wrappers."""
    assets = {}

    ike = Asset(
        name="IKE — ETF (world)",
        kind="currency",
        category="Stocks",
        profile="risky",
        wrapper="ike",
        icon="🌍",
        units="",
    )
    db.add(ike)
    db.flush()
    assets["ike"] = ike

    ikze = Asset(
        name="IKZE — bonds",
        kind="currency",
        category="Bonds",
        profile="safe",
        wrapper="ikze",
        icon="🛡️",
        units="",
    )
    db.add(ikze)
    db.flush()
    assets["ikze"] = ikze

    ppk = Asset(
        name="PPK",
        kind="currency",
        category="Retirement",
        profile="moderate",
        wrapper="ppk",
        icon="🏛️",
        units="",
    )
    db.add(ppk)
    db.flush()
    assets["ppk"] = ppk

    # Silver (metal) and Ethereum (crypto): opening-balance-only holdings, to
    # exercise the two new asset kinds in demo data without adding another
    # month-by-month story (see Watches below for the same "one snapshot"
    # pattern).
    silver = Asset(
        name="Silver",
        kind="metal",
        category="Metals",
        profile="moderate",
        icon="🥈",
        units="XAG",
    )
    db.add(silver)
    db.flush()
    assets["silver"] = silver

    ethereum = Asset(
        name="Ethereum",
        kind="crypto",
        category="Crypto",
        profile="risky",
        icon="Ξ",
        units="ETH",
    )
    db.add(ethereum)
    db.flush()
    assets["ethereum"] = ethereum

    return assets


def _create_income_sources(db: Session) -> dict[str, IncomeSource]:
    """Create the three income sources."""
    sources = {}

    # 1. Software house (UoP) - ends 2026-03-31
    uop = IncomeSource(
        name="Software house (UoP)",
        kind="uop",
        currency="PLN",
        params={
            "gross_monthly": 14000.0,
            "kup": "standard",
            "creative_share": 0.6,
            "pit2": True,
            "ppk_employee": 0.02,
            "ppk_employer": 0.015,
            "young_relief": False,
            "ppk_employee_extra": 0.0,
            "ppk_employer_extra": 0.0,
            "accident_rate": 0.0167,
        },
        starts_on=date(2024, 1, 1),
        ends_on=date(2026, 3, 31),
        notes="",
    )
    db.add(uop)
    db.flush()
    sources["uop"] = uop

    # 2. Own JDG (B2B) - starts 2026-04-01
    b2b = IncomeSource(
        name="Own JDG — B2B contract",
        kind="b2b",
        currency="PLN",
        params={
            "billing": "daily",
            "rate": 1150.0,
            "units_per_month": 20.0,
            "costs_monthly": 600.0,
            "tax_form": "liniowy",
            "ryczalt_rate": 0.12,
            "zus_stage": "full",
            "custom_base": None,
            "sickness": True,
            "vat": "standard",
            "vat_rate": 0.23,
            "costs_vat_rate": 0.23,
        },
        starts_on=date(2026, 4, 1),
        ends_on=None,
        notes="",
    )
    db.add(b2b)
    db.flush()
    sources["b2b"] = b2b

    # 3. Flat rental (other) - starts 2025-06-01
    rental = IncomeSource(
        name="Flat rental (net)",
        kind="other",
        currency="PLN",
        params={"net_monthly": 2200.0},
        starts_on=date(2025, 6, 1),
        ends_on=None,
        notes="",
    )
    db.add(rental)
    db.flush()
    sources["other"] = rental

    return sources


def _create_income_entries(db: Session, sources: dict[str, IncomeSource]) -> None:
    """Create specific income entries that override defaults."""
    # December 2025 bonus from UoP
    entry1 = IncomeEntry(
        source_id=sources["uop"].id,
        month="2025-12",
        amount=21000.0,
        costs=0.0,
        override_net=None,
        notes="bonus",
    )
    db.add(entry1)

    # August 2026 B2B entry with reduced hours (holiday)
    entry2 = IncomeEntry(
        source_id=sources["b2b"].id,
        month="2026-08",
        amount=11500.0,
        costs=600.0,
        override_net=None,
        notes="10 days holiday",
    )
    db.add(entry2)


def _create_expenses(db: Session) -> list[Expense]:
    """Create recurring expenses. Returns the rows so the month-checklist
    breakdown below (_create_monthly_records) can look up which commitments
    applied to which seeded month - their ids are only assigned once the
    caller flushes the session."""
    expenses_data = [
        ("Mortgage installment", 3400.0, "monthly", "Housing", date(2021, 5, 10), date(2046, 5, 10)),
        ("Utilities", 650.0, "monthly", "Housing", date(2021, 5, 15), None),
        ("Internet & phone", 140.0, "monthly", "Subscriptions", date(2022, 1, 5), None),
        ("Streaming", 90.0, "monthly", "Subscriptions", date(2023, 3, 1), None),
        ("Gym", 180.0, "monthly", "Health", date(2024, 2, 1), None),
        ("Accountant (JDG)", 250.0, "monthly", "Business", date(2026, 4, 10), None),
        ("Car insurance OC/AC", 2400.0, "yearly", "Car", date(2025, 11, 10), None),
        ("Property tax", 900.0, "yearly", "Housing", date(2026, 3, 15), None),
        ("Water & sewage", 300.0, "quarterly", "Housing", date(2025, 10, 5), None),
        ("Laptop", 7800.0, "once", "Business", date(2026, 5, 20), None),
    ]

    created = []
    for name, amount, period, category, starts_on, ends_on in expenses_data:
        exp = Expense(
            name=name,
            amount=amount,
            currency="PLN",
            period=period,
            category=category,
            starts_on=starts_on,
            ends_on=ends_on,
            notes="",
        )
        db.add(exp)
        created.append(exp)
    return created


def _create_monthly_records(db: Session, expenses: list[Expense]) -> None:
    """Create monthly records for M0 to current month.

    Written the new "month checklist" way (WP-M): every commitment charged
    that month marked paid at its listed amount, plus other_spent making up
    the rest of the month's story-driven total - so the demo shows the new
    form already filled in rather than the old single "actual spent" figure.
    All expenses and records here are PLN, so no currency conversion is
    needed to total them.
    """
    from .services.budget import expenses_applying_in_month

    now = _now_warsaw()
    current_month_date = date(now.year, now.month, 1)
    m0_date = _add_months(current_month_date, -12)

    # Keyed by calendar month so the spikes land where the story puts them:
    # the laptop in May, Christmas in December.
    wiggle_by_month = {1: -450, 2: 1200, 3: -200, 4: 600, 5: 7800, 6: -800,
                       7: 150, 8: 400, 9: -300, 10: 300, 11: -100, 12: 2900}

    months = _months_range(m0_date, current_month_date)

    for idx, month_str in enumerate(months):
        wiggle = wiggle_by_month[int(month_str[5:7])]
        target_total = 8200.0 + wiggle

        # December gets special notes
        notes = "Christmas" if month_str.endswith("-12") else ""

        applying = expenses_applying_in_month(expenses, month_str)
        committed = sum(float(e.amount) for e in applying)
        # max(0, ...): the story-driven target can in principle fall below
        # what the commitments alone add up to (e.g. a yearly bill landing
        # in a low-wiggle month) - other_spent floors at 0 rather than going
        # negative, so actual_spent can be >= the old target in that case.
        other_spent = round(max(0.0, target_total - committed), 2)
        commitments_paid = [
            {
                "expense_id": e.id,
                "name": e.name,
                "amount": float(e.amount),
                "currency": e.currency,
                "paid": True,
            }
            for e in applying
        ]

        record = MonthlyRecord(
            month=month_str,
            income=0.0,
            actual_spent=round(committed + other_spent, 2),
            currency="PLN",
            notes=notes,
            commitments_paid=json.dumps(commitments_paid),
            other_spent=other_spent,
        )
        db.add(record)


def _create_portfolio_snapshots(db: Session, extra_assets: dict[str, Asset]) -> None:
    """Create position snapshots for all assets."""
    now = _now_warsaw()
    current_date = now.date()
    current_month_date = date(current_date.year, current_date.month, 1)

    # M0 is 12 months before current month
    m0_date = _add_months(current_month_date, -12)

    # Market factors per month (cycle)
    mkt_cycle = [0.012, -0.018, 0.025, 0.008, -0.035, 0.021, 0.015, -0.006, 0.019, 0.011, -0.012, 0.017, 0.009, 0.004]

    # Get all assets
    all_assets = db.query(Asset).all()
    asset_by_name = {a.name: a for a in all_assets}

    # Build snapshot months: M0-1 (opening) through current month
    # Snapshots on day 28 of each month, or today if before 28th for current month
    snapshot_dates = []
    check_date = _add_months(m0_date, -1)  # Start from M0-1

    while check_date <= current_date:
        if check_date.month == current_date.month and check_date.year == current_date.year:
            # Current month: use today if before 28th, else 28th
            snapshot_date = min(current_date, date(current_date.year, current_date.month, 28))
        else:
            # Past months: use the 28th
            snapshot_date = date(check_date.year, check_date.month, min(28, 31))

        snapshot_dates.append(snapshot_date)

        # Move to next month
        if check_date.month == 12:
            check_date = date(check_date.year + 1, 1, 1)
        else:
            check_date = date(check_date.year, check_date.month + 1, 1)

    # Calculate snapshots
    # Starting prices and values
    cash_value = 22000.0
    savings_value = 38000.0
    stocks_value = 61000.0
    ike_value = 19500.0
    ikze_value = 7800.0
    ppk_value = 11800.0
    tfi_value = 14000.0
    bonds_value = 30000.0
    gold_amount = 50.0  # grams
    gold_price = 395.0  # PLN per gram
    btc_amount = 0.13
    btc_price = 420000.0  # PLN
    watches_value = 25000.0

    # Flow rules
    # IKZE: +940 until March 2026, +1413 after
    # PPK: +490 until March 2026, then 0
    march_2026 = date(2026, 3, 31)

    for k, snapshot_date in enumerate(snapshot_dates):
        mkt = mkt_cycle[k % len(mkt_cycle)]

        # Determine if this is after March 2026
        after_march_2026 = snapshot_date > march_2026

        # Cash flow: cycling -1500, 0, +1500
        cash_flow = (k % 3 - 1) * 1500.0
        cash_value = cash_value + cash_flow
        pos = Position(
            asset_id=asset_by_name["Cash"].id,
            amount=cash_value,
            currency="PLN",
            value_in_base=cash_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=cash_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # Savings: +1200/month, growth 0.0033
        savings_flow = 600.0
        savings_value = savings_value * (1 + 0.0033) + savings_flow
        pos = Position(
            asset_id=asset_by_name["Savings"].id,
            amount=savings_value,
            currency="PLN",
            value_in_base=savings_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=savings_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # Stocks (taxable): +1500/month, growth mkt[k]
        stocks_flow = 1000.0
        stocks_value = stocks_value * (1 + mkt) + stocks_flow
        pos = Position(
            asset_id=asset_by_name["Stocks"].id,
            amount=stocks_value,
            currency="PLN",
            value_in_base=stocks_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=stocks_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # IKE ETF: +2355/month, growth mkt[k]
        ike_flow = 2355.0
        ike_value = ike_value * (1 + mkt) + ike_flow
        pos = Position(
            asset_id=extra_assets["ike"].id,
            amount=ike_value,
            currency="PLN",
            value_in_base=ike_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=ike_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # IKZE: different flow before/after March 2026, growth 0.004
        ikze_flow = 1413.0 if after_march_2026 else 940.0
        ikze_value = ikze_value * (1 + 0.004) + ikze_flow
        pos = Position(
            asset_id=extra_assets["ikze"].id,
            amount=ikze_value,
            currency="PLN",
            value_in_base=ikze_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=ikze_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # PPK: +490 until March 2026, then 0; growth mkt[k] * 0.6
        ppk_flow = 0.0 if after_march_2026 else 490.0
        ppk_value = ppk_value * (1 + mkt * 0.6) + ppk_flow
        pos = Position(
            asset_id=extra_assets["ppk"].id,
            amount=ppk_value,
            currency="PLN",
            value_in_base=ppk_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=ppk_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # TFI Funds: +500/month, growth mkt[k] * 0.7
        tfi_flow = 300.0
        tfi_value = tfi_value * (1 + mkt * 0.7) + tfi_flow
        pos = Position(
            asset_id=asset_by_name["TFI Funds"].id,
            amount=tfi_value,
            currency="PLN",
            value_in_base=tfi_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=tfi_flow if k > 0 else None,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # National Bonds: no flow, growth 0.0045
        bonds_value = bonds_value * (1 + 0.0045)
        pos = Position(
            asset_id=asset_by_name["National Bonds"].id,
            amount=bonds_value,
            currency="PLN",
            value_in_base=bonds_value,
            price_used=1.0,
            base_currency="PLN",
            flow_in_base=0.0 if k > 0 else None,  # interest only, nothing moved
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # Gold: no flow, price grows with mkt * 0.5
        gold_price = gold_price * (1 + mkt * 0.5)
        gold_value = gold_amount * gold_price
        pos = Position(
            asset_id=asset_by_name["Gold"].id,
            amount=gold_amount,
            currency="PLN",
            value_in_base=gold_value,
            price_used=gold_price,
            base_currency="PLN",
            flow_in_base=0.0 if k > 0 else None,  # quantity unchanged
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # Bitcoin: +0.02 BTC in February 2026, price grows with mkt * 3
        btc_flow_amount = 0.0
        if snapshot_date.year == 2026 and snapshot_date.month == 2:
            btc_flow_amount = 0.02

        btc_price = btc_price * (1 + mkt * 3)
        btc_amount = btc_amount + btc_flow_amount
        btc_flow_base = (btc_flow_amount * btc_price) if k > 0 else None
        btc_value = btc_amount * btc_price

        pos = Position(
            asset_id=asset_by_name["Bitcoin"].id,
            amount=btc_amount,
            currency="PLN",
            value_in_base=btc_value,
            price_used=btc_price,
            base_currency="PLN",
            flow_in_base=btc_flow_base,
            timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
        )
        db.add(pos)

        # Watches: only opening snapshot
        if k == 0:
            pos = Position(
                asset_id=asset_by_name["Watches"].id,
                amount=watches_value,
                currency="PLN",
                value_in_base=watches_value,
                price_used=1.0,
                base_currency="PLN",
                flow_in_base=None,  # Opening snapshot
                timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
            )
            db.add(pos)

        # Silver and Ethereum: opening snapshot only, same pattern as
        # Watches - the story does not need a full growth curve to exercise
        # kind="metal" / a second crypto symbol.
        if k == 0:
            silver_amount = 2000.0  # grams
            silver_price = 8.1  # PLN per gram, approx (~64 USD/oz)
            pos = Position(
                asset_id=asset_by_name["Silver"].id,
                amount=silver_amount,
                currency="PLN",
                value_in_base=silver_amount * silver_price,
                price_used=silver_price,
                base_currency="PLN",
                flow_in_base=None,
                timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
            )
            db.add(pos)

            eth_amount = 1.5
            eth_price = 10500.0  # PLN per coin, approx (~2700 USD)
            pos = Position(
                asset_id=asset_by_name["Ethereum"].id,
                amount=eth_amount,
                currency="PLN",
                value_in_base=eth_amount * eth_price,
                price_used=eth_price,
                base_currency="PLN",
                flow_in_base=None,
                timestamp=datetime.combine(snapshot_date, datetime.min.time()).replace(hour=12, tzinfo=tz.utc),
            )
            db.add(pos)


def _create_fire_settings(db: Session) -> None:
    """Create FIRE settings."""
    fire_data = {
        "birth_year": 1992,
        "target_fi_age": 50,
        "retirement_age": 60,
        "swr": 0.035,
        "inflation": 0.035,
        "zus_pension_monthly": 3200,
        "barista_income_monthly": 4000,
        "include_health_cost": True,
        "gain_share": 0.5,
        "emergency_months": 6,
    }

    import json
    setting = Setting(key="fire", value=json.dumps(fire_data))
    db.add(setting)


def main() -> int:
    """Main entry point."""
    print("demo_seed: starting")

    # Check safety (database type)
    _check_safety()

    # Create/migrate schema. Feature-flag seeding is deliberately deferred to
    # after the demo data is written (see below): seed_features() only ever
    # sets its default once, and running it here - before any position or
    # income row exists - would permanently lock this wallet to "new,
    # everything off" despite being fully populated a few lines later.
    print("demo_seed: initializing schema")
    Base.metadata.create_all(bind=engine)
    migrate()
    seed()
    backfill_profiles()

    db = SessionLocal()
    try:
        # Check that database is empty
        _check_empty(db)

        print("demo_seed: creating income sources")
        sources = _create_income_sources(db)

        print("demo_seed: creating income entries")
        _create_income_entries(db, sources)

        print("demo_seed: creating expenses")
        expenses = _create_expenses(db)
        db.flush()  # assign expense ids before the month checklist needs them

        print("demo_seed: creating monthly records")
        _create_monthly_records(db, expenses)

        print("demo_seed: creating extra assets (IKE, IKZE, PPK, Silver, Ethereum)")
        extra_assets = _create_extra_assets(db)

        print("demo_seed: creating portfolio snapshots")
        _create_portfolio_snapshots(db, extra_assets)

        print("demo_seed: creating FIRE settings")
        _create_fire_settings(db)

        db.commit()
        print(f"demo_seed: wrote to {settings.database_url}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()

    print("demo_seed: seeding feature defaults")
    seed_features()
    return 0


if __name__ == "__main__":
    sys.exit(main())
