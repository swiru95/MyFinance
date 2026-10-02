"""Wallet export and import (see schemas/wallet.py for the file format).

Export reads one user's wallet through their own session and writes the
*setup* only: active assets in their current state, income sources, active
recurring expenses and the settings that shape the wallet. No history, no
monthly figures, no ids, nothing that identifies the person.

Import is plan-then-write. `build_plan` looks at the caller's wallet and the
(already fully validated) file and decides, item by item, what would be
created, what would fill an existing empty asset, and what is left alone
because something of theirs is already there. `preview` shows that plan;
`apply` writes it in one transaction through the same user-scoped session as
any other write, so every row is stamped with the caller and encrypted under
the caller's key. Nothing is ever overwritten or deleted.

The rule for a wallet that already has data, in one line: *import only adds*.
  - Settings: a value is applied only if the wallet has not set it yet.
  - Assets: a file asset matches only one of your active assets with the same
    name (case-insensitive) and shape. If that asset has no balance (the
    default asset types of a new account, typically) it is placed on it
    instead of creating a duplicate; if it has a balance the file asset is
    skipped; otherwise a new asset is created, even if that leaves an empty
    default asset unused.
  - Income sources and expenses: an identical one that already exists is
    skipped; anything else is created.
Running the same import twice therefore changes nothing the second time.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models.asset import Asset
from ..models.expense import Expense
from ..models.income import IncomeSource
from ..models.position import Position
from ..models.settings import Setting
from ..models.user import User
from ..routes.helpers import (
    compute_value,
    convert_currency,
    get_base_currency,
    get_features,
    get_timezone,
    latest_positions_by_asset,
    today_in,
)
from ..schemas.fire import FireSettings
from ..schemas.wallet import (
    FIRE_MONEY_FIELDS,
    FORMAT,
    INCOME_MONEY_PARAMS,
    VERSION,
    ImportPlanOut,
    PlanCounts,
    PlanItem,
    PlanWarning,
    WalletAsset,
    WalletExpense,
    WalletFile,
    WalletIncomeSource,
    fmt_amount,
)
from .growth import portfolio_growth
from .price_service import PriceService

# A paid-in total within this of the current value is "the same": no separate
# baseline position is needed (see _positions_for).
_SAME = Decimal("0.005")


# --- Export -------------------------------------------------------------------


def _money_params(params: dict) -> dict:
    out = dict(params)
    for key in INCOME_MONEY_PARAMS & set(out):
        if out[key] is not None:
            out[key] = fmt_amount(repr(float(out[key])))
    return out


def build_export(db: Session, user_id: uuid.UUID) -> dict:
    from ..routes.expenses import _status

    today = today_in(db)
    base = get_base_currency(db)

    fire_row = db.query(Setting).filter(Setting.key == "fire").first()
    fire = None
    if fire_row and fire_row.value:
        fire = FireSettings.model_validate(json.loads(fire_row.value)).model_dump()
        for key in FIRE_MONEY_FIELDS:
            if fire.get(key) is not None:
                fire[key] = fmt_amount(repr(float(fire[key])))
    user = db.get(User, user_id)

    # Current value and paid-in total come from the growth service, so they are
    # exactly what the Assets page shows for each asset.
    growth = {a["asset_id"]: a for a in portfolio_growth(db)["assets"]}
    latest = latest_positions_by_asset(db)
    assets = []
    for asset in sorted(db.query(Asset).all(), key=lambda a: a.id):
        pos = latest.get(asset.id)
        if asset.archived_at is not None or pos is None:
            continue
        g = growth.get(asset.id)
        value = g["value"] if g else float(pos.value_in_base)
        invested = g["invested"] if g else None
        assets.append({
            "name": asset.name,
            "kind": asset.kind,
            "category": asset.category,
            "units": asset.units,
            "interest_basis": asset.interest_basis,
            "profile": asset.profile,
            "icon": asset.icon,
            "wrapper": asset.wrapper,
            "currency": pos.currency,
            "amount": fmt_amount(pos.amount),
            "value": fmt_amount(value),
            # Unknown / not meaningful (e.g. net withdrawals) is null, not 0.
            "contributed": fmt_amount(invested) if invested is not None and invested > 0 else None,
            "accrues_from": pos.accrues_from.isoformat() if pos.accrues_from else None,
        })

    sources = []
    for s in sorted(db.query(IncomeSource).all(), key=lambda s: (s.starts_on, s.id)):
        sources.append({
            "name": s.name,
            "kind": s.kind,
            "currency": s.currency,
            "params": _money_params(s.params or {}),
            "starts_on": s.starts_on.isoformat(),
            "ends_on": s.ends_on.isoformat() if s.ends_on else None,
            "notes": s.notes,
        })

    expenses = []
    for e in sorted(db.query(Expense).all(), key=lambda e: (e.starts_on, e.id)):
        if e.period == "once" or _status(e, today) != "active":
            continue
        expenses.append({
            "name": e.name,
            "amount": fmt_amount(e.amount),
            "currency": e.currency,
            "period": e.period,
            "category": e.category,
            "starts_on": e.starts_on.isoformat(),
            "ends_on": e.ends_on.isoformat() if e.ends_on else None,
            "notes": e.notes,
        })

    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "settings": {
            "base_currency": base,
            "timezone": get_timezone(db),
            "features": get_features(db).model_dump(),
            "fire": fire,
            "birth_year": user.birth_year if user else None,
        },
        "assets": assets,
        "income_sources": sources,
        "expenses": expenses,
    }


# --- Import -------------------------------------------------------------------


@dataclass
class _AssetWrite:
    file: WalletAsset
    target: Asset | None  # an existing empty asset to fill, else None (create)


@dataclass
class Plan:
    items: list[PlanItem] = field(default_factory=list)
    warnings: list[PlanWarning] = field(default_factory=list)
    # What apply() writes.
    settings: dict[str, str] = field(default_factory=dict)  # setting key -> value
    birth_year: int | None = None
    assets: list[_AssetWrite] = field(default_factory=list)
    sources: list[WalletIncomeSource] = field(default_factory=list)
    expenses: list[WalletExpense] = field(default_factory=list)
    effective_base: str = "PLN"
    file_base: str = "PLN"

    def counts(self) -> dict[str, PlanCounts]:
        out = {s: PlanCounts() for s in ("setting", "asset", "income_source", "expense")}
        for it in self.items:
            setattr(out[it.section], it.action, getattr(out[it.section], it.action) + 1)
        return out

    def writes(self) -> int:
        n = len(self.settings) + (1 if self.birth_year is not None else 0)
        n += len(self.sources) + len(self.expenses)
        for w in self.assets:
            n += (0 if w.target is not None else 1) + 1  # asset row, opening position
        return n


def _asset_key(kind: str, category: str, units: str, wrapper: str, basis: str) -> tuple:
    return (kind, (category or "").casefold(), (units or "").upper(), wrapper or "", basis or "")


def _file_key(a: WalletAsset) -> tuple:
    return _asset_key(a.kind, a.category, a.units, a.wrapper, a.interest_basis)


def _setting_row(db: Session, key: str) -> Setting | None:
    return db.query(Setting).filter(Setting.key == key).first()


def build_plan(db: Session, user_id: uuid.UUID, wallet: WalletFile) -> Plan:
    plan = Plan()
    ws = wallet.settings

    # -- settings: apply only what the wallet has not set --------------------
    def decide(key: str, name: str, incoming: str | None, shown: str | None = None):
        if incoming is None:
            return
        row = _setting_row(db, key)
        if row is None or not row.value:
            plan.settings[key] = incoming
            plan.items.append(PlanItem(
                section="setting", name=name, action="create", reason="new",
                incoming=shown or incoming))
        elif _same_json(row.value, incoming):
            plan.items.append(PlanItem(
                section="setting", name=name, action="keep", reason="unchanged",
                existing=shown or incoming, incoming=shown or incoming))
        else:
            plan.items.append(PlanItem(
                section="setting", name=name, action="keep", reason="already_set",
                existing=_short(row.value), incoming=shown or _short(incoming)))

    decide("base_currency", "base_currency", ws.base_currency)
    decide("timezone", "timezone", ws.timezone)
    decide("features", "features", ws.features.model_dump_json() if ws.features else None)
    decide("fire", "fire", ws.fire.model_dump_json() if ws.fire else None)

    if ws.birth_year is not None:
        user = db.get(User, user_id)
        have = user.birth_year if user else None
        if have is None:
            plan.birth_year = ws.birth_year
            plan.items.append(PlanItem(
                section="setting", name="birth_year", action="create", reason="new",
                incoming=str(ws.birth_year)))
        else:
            plan.items.append(PlanItem(
                section="setting", name="birth_year", action="keep",
                reason="unchanged" if have == ws.birth_year else "already_set",
                existing=str(have), incoming=str(ws.birth_year)))

    # The base currency the wallet will have once this runs.
    plan.file_base = ws.base_currency
    plan.effective_base = plan.settings.get("base_currency") or get_base_currency(db)
    if plan.file_base != plan.effective_base and wallet.assets:
        plan.warnings.append(PlanWarning(
            code="base_currency_differs", args=[plan.file_base, plan.effective_base]))

    # -- assets ---------------------------------------------------------------
    active = sorted(
        (a for a in db.query(Asset).all() if a.archived_at is None), key=lambda a: a.id
    )
    has_balance = {p_asset for p_asset in latest_positions_by_asset(db)}
    empty = [a for a in active if a.id not in has_balance]
    taken: set[int] = set()  # existing empty assets already claimed by a file asset

    def claim(candidates: list[Asset], pick) -> Asset | None:
        for a in candidates:
            if a.id not in taken and pick(a):
                taken.add(a.id)
                return a
        return None

    matches: dict[int, Asset | None] = {}
    # Only an empty asset with the same name (case-insensitive) and shape is filled;
    # a shape-only match would silently swallow the file's own asset name.
    for i, fa in enumerate(wallet.assets):
        key = _file_key(fa)
        matches[i] = claim(
            empty,
            lambda a, fa=fa, key=key: a.name.casefold() == fa.name.casefold()
            and _asset_key(a.kind, a.category, a.units, a.wrapper, a.interest_basis) == key,
        )

    for i, fa in enumerate(wallet.assets):
        target = matches[i]
        if target is not None:
            plan.assets.append(_AssetWrite(fa, target))
            plan.items.append(PlanItem(
                section="asset", name=fa.name, action="fill", reason="default_type",
                existing=target.name))
            continue
        same_with_balance = next(
            (a for a in active
             if a.id in has_balance and a.name.casefold() == fa.name.casefold()
             and _asset_key(a.kind, a.category, a.units, a.wrapper, a.interest_basis)
             == _file_key(fa)),
            None,
        )
        if same_with_balance is not None:
            plan.items.append(PlanItem(
                section="asset", name=fa.name, action="skip",
                reason="already_has_balance", existing=same_with_balance.name))
            continue
        plan.assets.append(_AssetWrite(fa, None))
        plan.items.append(PlanItem(section="asset", name=fa.name, action="create", reason="new"))

    # -- income sources / expenses: add what is not already there --------------
    have_sources = {
        (s.name.casefold(), s.kind, s.starts_on) for s in db.query(IncomeSource).all()
    }
    seen: set = set()
    for src in wallet.income_sources:
        key = (src.name.casefold(), src.kind, src.starts_on)
        if key in have_sources or key in seen:
            plan.items.append(PlanItem(
                section="income_source", name=src.name, action="skip", reason="already_exists",
                existing=src.name))
            continue
        seen.add(key)
        plan.sources.append(src)
        plan.items.append(PlanItem(section="income_source", name=src.name, action="create"))

    have_expenses = {
        (e.name.casefold(), Decimal(str(e.amount)), e.currency, e.period, e.starts_on)
        for e in db.query(Expense).all()
    }
    seen = set()
    for ex in wallet.expenses:
        key = (ex.name.casefold(), ex.amount_d, ex.currency, ex.period, ex.starts_on)
        if key in have_expenses or key in seen:
            plan.items.append(PlanItem(
                section="expense", name=ex.name, action="skip", reason="already_exists",
                existing=ex.name))
            continue
        seen.add(key)
        plan.expenses.append(ex)
        plan.items.append(PlanItem(section="expense", name=ex.name, action="create"))

    return plan


def _same_json(stored: str, incoming: str) -> bool:
    try:
        return json.loads(stored) == json.loads(incoming)
    except ValueError:
        return stored == incoming


def _short(value: str, limit: int = 120) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def preview(db: Session, user_id: uuid.UUID, wallet: WalletFile) -> ImportPlanOut:
    plan = build_plan(db, user_id, wallet)
    return _out(plan, applied=False)


def _out(plan: Plan, *, applied: bool) -> ImportPlanOut:
    return ImportPlanOut(
        applied=applied,
        items=plan.items,
        counts=plan.counts(),
        warnings=plan.warnings,
        writes=plan.writes(),
    )


def _positions_for(
    db: Session,
    asset: Asset,
    fa: WalletAsset,
    contributed: Decimal | None,
    when: datetime,
) -> list[Position]:
    """The opening position of an imported asset.

    One position holding the current amount, valued at today's prices.

    The data model keeps "money you paid in" only as the opening value plus the
    flows recorded on later snapshots, so a paid-in total that differs from
    today's value (the asset has grown, or lost) cannot be carried by a single
    snapshot without lying about its value. In that case a baseline snapshot is
    written one millisecond ahead of the real one, valued at what was paid in
    and carrying no flow, followed by the real one with a recorded flow of zero.
    "Your money" then reads the paid-in total and "growth" the difference, as in
    the source wallet; the stored value of the *latest* snapshot stays true, so
    totals, charts and effective spend are not skewed.
    """
    amount = fa.amount_d
    value, price, base = compute_value(db, asset, float(amount), fa.currency, fa.accrues_from)
    real = Position(
        asset_id=asset.id, amount=amount, currency=fa.currency,
        value_in_base=round(value, 4), price_used=round(price, 6), base_currency=base,
        notes="imported", accrues_from=fa.accrues_from, flow_in_base=None, timestamp=when,
    )
    if contributed is None or abs(Decimal(str(round(value, 4))) - contributed) <= _SAME:
        return [real]
    baseline = Position(
        asset_id=asset.id, amount=amount, currency=fa.currency,
        value_in_base=contributed, price_used=round(price, 6), base_currency=base,
        notes="imported: amount paid in", accrues_from=fa.accrues_from,
        flow_in_base=None, timestamp=when,
    )
    real.timestamp = when + timedelta(milliseconds=1)
    real.flow_in_base = Decimal(0)
    return [baseline, real]


def apply(db: Session, user_id: uuid.UUID, wallet: WalletFile) -> ImportPlanOut:
    """Write the plan in one transaction (the session's), or nothing."""
    plan = build_plan(db, user_id, wallet)
    try:
        for key, value in plan.settings.items():
            db.add(Setting(key=key, value=value))
        if plan.birth_year is not None:
            db.get(User, user_id).birth_year = plan.birth_year
        # Prices below are read in the base currency the wallet will have.
        db.flush()

        ps = PriceService(plan.effective_base)
        when = datetime.now(timezone.utc)
        for w in plan.assets:
            fa = w.file
            asset = w.target
            if asset is None:
                asset = Asset(
                    name=fa.name, kind=fa.kind, category=fa.category,
                    interest_basis=fa.interest_basis, profile=fa.profile, icon=fa.icon,
                    units=fa.units, wrapper=fa.wrapper,
                )
                db.add(asset)
                db.flush()
            contributed = fa.contributed_d
            if contributed is not None and plan.file_base != plan.effective_base:
                contributed = Decimal(str(round(
                    convert_currency(ps, float(contributed), plan.file_base, plan.effective_base),
                    4)))
            for p in _positions_for(db, asset, fa, contributed, when):
                db.add(p)

        for s in plan.sources:
            db.add(IncomeSource(
                name=s.name, kind=s.kind, currency=s.currency, params=s.params,
                starts_on=s.starts_on, ends_on=s.ends_on, notes=s.notes,
            ))
        for e in plan.expenses:
            db.add(Expense(
                name=e.name, amount=e.amount_d, currency=e.currency, period=e.period,
                category=e.category, starts_on=e.starts_on, ends_on=e.ends_on, notes=e.notes,
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return _out(plan, applied=True)

