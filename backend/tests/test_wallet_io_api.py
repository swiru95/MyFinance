"""Wallet export / import through the API: what the file holds, how a preview
and an import treat a fresh and a non-empty wallet, isolation between users,
and what a bad file does (nothing).

Alice and Bob are real bearer-token clients against a fake OIDC issuer
(conftest.two_users); both start as brand-new accounts with the default asset
types.
"""
from __future__ import annotations

import json

import pytest

from tests.conftest import make_client, make_user, raw, session_for
from tests.test_wallet_io import ALL_ON, CASH, _ok, _post_file, _wallet

TABLES = ("assets", "positions", "expenses", "income_sources", "settings",
          "income_entries", "monthly_records", "reports", "insights")


@pytest.fixture
def users(two_users):
    """Alice and Bob, both already signed in once: the first request of a new
    account creates it (and its default asset types), which would otherwise show
    up as a change in the row counts the tests compare."""
    for c in two_users:
        _ok(c.get("/api/auth/me"))
    return two_users


def _row_counts() -> dict:
    """{(table, user): rows} straight from the database, every user."""
    out = {}
    for table in TABLES:
        for user, n in raw(f"SELECT user_id, count(*) FROM {table} GROUP BY user_id"):
            out[(table, str(user).replace("-", ""))] = n
    return out


def _changed_users(before: dict, after: dict) -> set:
    return {u for (t, u) in set(before) | set(after)
            if before.get((t, u), 0) != after.get((t, u), 0)}


def _alice_setup(c) -> None:
    """A wallet with a bit of everything, history and excluded things included."""
    _ok(c.put("/api/settings", json={"base_currency": "EUR", "timezone": "Europe/London",
                                      "features": ALL_ON}))
    _ok(c.put("/api/settings/birth-year", json={"birth_year": 1990}))
    _ok(c.put("/api/fire/settings", json={"birth_year": 1990, "target_fi_age": 55,
                                           "zus_pension_monthly": 2500.5}))
    assets = {a["name"]: a for a in _ok(c.get("/api/assets"))}
    cash = assets["Cash"]
    # history: three updates with deposits
    _ok(c.post("/api/positions", json={"asset_id": cash["id"], "amount": 1000, "currency": "EUR"}), 201)
    _ok(c.post("/api/positions", json={"asset_id": cash["id"], "amount": 2000, "currency": "EUR", "flow": 900}), 201)
    _ok(c.post("/api/positions", json={"asset_id": cash["id"], "amount": 2600.55, "currency": "EUR", "flow": 500}), 201)
    _ok(c.post("/api/positions", json={"asset_id": assets["Gold"]["id"], "amount": 12.5, "currency": "EUR"}), 201)
    # an asset that is archived afterwards, with a closing snapshot
    arch = _ok(c.post("/api/assets", json={"name": "OldFund", "kind": "currency", "category": "TFI"}), 201)
    _ok(c.post("/api/positions", json={"asset_id": arch["id"], "amount": 77, "currency": "EUR"}), 201)
    _ok(c.post(f"/api/assets/{arch['id']}/archive"))
    _ok(c.post("/api/expenses", json={"name": "Rent", "amount": 1500.5, "currency": "EUR",
                                       "period": "monthly", "starts_on": "2025-01-01", "category": "Housing"}), 201)
    _ok(c.post("/api/expenses", json={"name": "Insurance", "amount": 600, "currency": "EUR",
                                       "period": "yearly", "starts_on": "2025-03-01"}), 201)
    _ok(c.post("/api/expenses", json={"name": "Old gym", "amount": 50, "currency": "EUR",
                                       "period": "monthly", "starts_on": "2024-01-01", "ends_on": "2024-12-31"}), 201)
    _ok(c.post("/api/expenses", json={"name": "Sofa", "amount": 900, "currency": "EUR",
                                       "period": "once", "starts_on": "2025-05-01"}), 201)
    src = _ok(c.post("/api/income/sources", json={
        "name": "Job", "kind": "uop", "currency": "EUR",
        "params": {"gross_monthly": 8000.25, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2025-01-01"}), 201)
    _ok(c.put(f"/api/income/sources/{src['id']}/entries/2025-02",
              json={"amount": 9999, "override_net": 7000, "notes": "bonus"}))
    _ok(c.put("/api/monthly/2025-02", json={"income": 100, "actual_spent": 200,
                                             "currency": "EUR", "notes": "private note"}))


def _file(c) -> dict:
    r = c.get("/api/wallet/export")
    assert r.status_code == 200
    return r.json()


# --- export ---------------------------------------------------------------------


def test_export_is_setup_only(users):
    alice, _ = users
    _alice_setup(alice)
    r = alice.get("/api/wallet/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"].startswith('attachment; filename="myfinance-wallet-')
    assert r.headers["cache-control"] == "no-store"
    text = r.text
    f = json.loads(text)
    assert (f["format"], f["version"]) == ("myfinance-wallet", 1)
    assert set(f) == {"format", "version", "exported_at", "settings", "assets",
                      "income_sources", "expenses"}
    assert f["settings"]["base_currency"] == "EUR"
    assert f["settings"]["timezone"] == "Europe/London"
    assert f["settings"]["birth_year"] == 1990
    assert f["settings"]["fire"]["birth_year"] == 1990
    assert f["settings"]["fire"]["zus_pension_monthly"] == "2500.5"

    # Active assets with a balance only: no archived one, no empty default types.
    assert {a["name"] for a in f["assets"]} == {"Cash", "Gold"}
    cash = next(a for a in f["assets"] if a["name"] == "Cash")
    assert cash["amount"] == "2600.55"
    assert cash["contributed"] == "2400"  # 1000 opening + 900 + 500
    assert isinstance(cash["value"], str)
    # Recurring and active only: not the ended one, not the one-off.
    assert {e["name"] for e in f["expenses"]} == {"Rent", "Insurance"}
    assert next(e for e in f["expenses"] if e["name"] == "Rent")["amount"] == "1500.5"
    # Income sources with parameters, money as strings.
    assert f["income_sources"][0]["params"]["gross_monthly"] == "8000.25"

    # Nothing of the excluded kinds, no ids, nothing identifying.
    for word in ("bonus", "private note", "OldFund", "Sofa", "Old gym", "asset_id",
                 "user", "email", "recovery", "terms", "subject", "wrapped", "9999"):
        assert word not in text, word
    assert '"id"' not in text


def test_empty_wallet_exports_a_valid_file(users):
    from src.schemas.wallet import WalletFile

    _, bob = users
    f = _file(bob)
    assert f["assets"] == [] and f["expenses"] == [] and f["income_sources"] == []
    WalletFile.model_validate(f)


def test_wallet_endpoints_require_sign_in(idp):
    anon = make_client()
    assert anon.get("/api/wallet/export").status_code == 401
    assert anon.post("/api/wallet/import/preview", content=b"{}").status_code == 401
    assert anon.post("/api/wallet/import", content=b"{}").status_code == 401


# --- preview and import into a fresh account ----------------------------------------


def test_preview_writes_nothing_then_import_creates(users):
    alice, bob = users
    _alice_setup(alice)
    f = _file(alice)
    before = _row_counts()
    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    assert prev["applied"] is False
    assert _row_counts() == before
    by = {(i["section"], i["name"]): i for i in prev["items"]}
    # Cash and Gold land on Bob's own empty default types instead of duplicating them.
    assert (by[("asset", "Cash")]["action"], by[("asset", "Cash")]["reason"]) == ("fill", "default_type")
    assert by[("asset", "Gold")]["action"] == "fill"
    assert by[("expense", "Rent")]["action"] == "create"
    assert by[("setting", "base_currency")]["action"] == "create"
    assert prev["counts"]["asset"]["fill"] == 2

    done = _ok(_post_file(bob, "/api/wallet/import", f))
    assert done["applied"] is True
    assert done["counts"] == prev["counts"]
    assert len(_changed_users(before, _row_counts())) == 1

    assert len(_ok(bob.get("/api/assets"))) == 9  # no duplicates of the default types
    s = _ok(bob.get("/api/settings"))
    assert s["base_currency"] == "EUR" and s["timezone"] == "Europe/London"
    assert s["features"] == ALL_ON and s["birth_year"] == 1990
    assert _ok(bob.get("/api/fire/settings"))["zus_pension_monthly"] == 2500.5
    names = {a["id"]: a["name"] for a in _ok(bob.get("/api/assets"))}
    growth = {names[a["asset_id"]]: a for a in _ok(bob.get("/api/positions/growth"))["assets"]}
    assert growth["Cash"]["invested"] == 2400.0  # "your money" carried over
    assert growth["Cash"]["value"] == 2600.55
    assert growth["Cash"]["growth"] == 200.55
    assert {e["name"] for e in _ok(bob.get("/api/expenses"))} == {"Rent", "Insurance"}
    assert [x["name"] for x in _ok(bob.get("/api/income/sources"))] == ["Job"]
    # No history came along.
    feb = _ok(bob.get("/api/monthly/2025-02"))
    assert feb["saved"] is False and feb["actual_spent"] == 0 and feb["notes"] == ""
    assert raw("SELECT count(*) FROM income_entries")[0][0] == 1  # Alice's own, not copied


def test_one_position_when_there_is_nothing_to_carry(users):
    _, bob = users
    f = _wallet(assets=[{**CASH, "contributed": "1500.5"},
                        {**CASH, "name": "Savings", "category": "Savings", "contributed": None}])
    _ok(_post_file(bob, "/api/wallet/import", f))
    assert raw("SELECT count(*) FROM positions")[0][0] == 2  # one each


def test_paid_in_total_is_carried_with_a_baseline(users):
    _, bob = users
    _ok(_post_file(bob, "/api/wallet/import", _wallet(assets=[{**CASH, "contributed": "1000"}])))
    t = _ok(bob.get("/api/positions/growth"))["total"]
    assert (t["invested"], t["value"], t["growth"]) == (1000.0, 1500.5, 500.5)
    assert t["untracked_updates"] == 0
    # The latest snapshot holds the true value, so totals do not skew.
    assert _ok(bob.get("/api/summary"))["total_value"] == 1500.5
    assert raw("SELECT count(*) FROM positions")[0][0] == 2


def test_a_loss_is_carried_too(users):
    _, bob = users
    f = _wallet(assets=[{**CASH, "amount": "800", "value": "800", "contributed": "1000"}])
    _ok(_post_file(bob, "/api/wallet/import", f))
    t = _ok(bob.get("/api/positions/growth"))["total"]
    assert (t["invested"], t["value"], t["growth"]) == (1000.0, 800.0, -200.0)


# --- a wallet that already has data: only adds ------------------------------------------


def test_import_into_a_non_empty_wallet_only_adds(users):
    alice, bob = users
    _alice_setup(alice)
    f = _file(alice)

    # Bob already has a Cash balance, a different base currency and one rent.
    _ok(bob.put("/api/settings", json={"base_currency": "USD", "features": {"portfolio": True}}))
    cash = next(a for a in _ok(bob.get("/api/assets")) if a["name"] == "Cash")
    _ok(bob.post("/api/positions", json={"asset_id": cash["id"], "amount": 10, "currency": "USD"}), 201)
    _ok(bob.post("/api/expenses", json={"name": "Rent", "amount": 1500.5, "currency": "EUR",
                                         "period": "monthly", "starts_on": "2025-01-01"}), 201)

    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    by = {(i["section"], i["name"]): i for i in prev["items"]}
    assert (by[("asset", "Cash")]["action"], by[("asset", "Cash")]["reason"]) == ("skip", "already_has_balance")
    assert by[("asset", "Gold")]["action"] == "fill"
    assert by[("expense", "Rent")]["action"] == "skip"
    assert by[("expense", "Insurance")]["action"] == "create"
    assert (by[("setting", "base_currency")]["action"], by[("setting", "base_currency")]["reason"]) \
        == ("keep", "already_set")
    assert by[("setting", "base_currency")]["existing"] == "USD"
    assert by[("setting", "features")]["action"] == "keep"
    assert by[("setting", "fire")]["action"] == "create"
    assert {"code": "base_currency_differs", "args": ["EUR", "USD"]} in prev["warnings"]

    _ok(_post_file(bob, "/api/wallet/import", f))
    s = _ok(bob.get("/api/settings"))
    assert s["base_currency"] == "USD"  # never overwritten
    assert s["features"]["portfolio"] is True and s["features"]["tax"] is False
    # Cash balance untouched, Rent not duplicated.
    pos = {p["asset_id"]: p for p in _ok(bob.get("/api/positions"))}
    assert pos[cash["id"]]["amount"] == 10
    assert sorted(e["name"] for e in _ok(bob.get("/api/expenses"))) == ["Insurance", "Rent"]
    assert _ok(bob.get("/api/positions/growth"))["base_currency"] == "USD"

    # Importing the same file again changes nothing.
    before = _row_counts()
    again = _ok(_post_file(bob, "/api/wallet/import", f))
    assert again["writes"] == 0
    assert all(i["action"] in ("skip", "keep") for i in again["items"])
    assert _row_counts() == before


def test_paid_in_total_is_converted_into_the_wallets_own_base_currency(users):
    _, bob = users
    _ok(bob.put("/api/settings", json={"base_currency": "USD"}))
    f = _wallet(  # the file is in PLN, Bob's wallet in USD
        assets=[{**CASH, "currency": "PLN", "amount": "1000", "value": "1000", "contributed": "400"}])
    _ok(_post_file(bob, "/api/wallet/import", f))
    t = _ok(bob.get("/api/positions/growth"))["total"]
    assert t["value"] < 1000  # 1000 PLN in dollars
    assert 0 < t["invested"] < t["value"]  # 400 PLN, converted, not left as 400
    assert abs(t["invested"] / t["value"] - 0.4) < 0.001


def test_fill_never_changes_the_existing_asset(users):
    _, bob = users
    before = {a["name"]: a for a in _ok(bob.get("/api/assets"))}
    # Same name (any case) and shape as the default Cash; other fields differ.
    f = _wallet(assets=[{**CASH, "name": "cash", "icon": "Z", "profile": "risky"}])
    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    item = next(i for i in prev["items"] if i["section"] == "asset")
    assert (item["action"], item["existing"]) == ("fill", "Cash")
    _ok(_post_file(bob, "/api/wallet/import", f))
    assert {a["name"]: a for a in _ok(bob.get("/api/assets"))} == before  # only a position was added


def test_a_different_name_is_never_matched_by_shape(users):
    _, bob = users
    f = _wallet(assets=[{**CASH, "name": "My wallet"}])  # same shape as the empty default Cash
    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    assert next(i for i in prev["items"] if i["section"] == "asset")["action"] == "create"
    _ok(_post_file(bob, "/api/wallet/import", f))
    assets = _ok(bob.get("/api/assets"))
    assert len(assets) == 10 and "My wallet" in {a["name"] for a in assets}
    pos = {p["asset_id"]: p for p in _ok(bob.get("/api/positions"))}
    cash = next(a for a in assets if a["name"] == "Cash")
    assert cash["id"] not in pos  # the empty default stays unused


def test_assets_that_match_nothing_are_created(users):
    _, bob = users
    f = _wallet(assets=[{**CASH, "name": "Brokerage", "category": "Brokerage", "icon": ""}])
    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    assert next(i for i in prev["items"] if i["section"] == "asset")["action"] == "create"
    _ok(_post_file(bob, "/api/wallet/import", f))
    assets = _ok(bob.get("/api/assets"))
    assert "Brokerage" in {a["name"] for a in assets} and len(assets) == 10


# --- isolation -----------------------------------------------------------------------


def test_import_only_touches_the_caller(users):
    alice, bob = users
    _alice_setup(alice)
    f = _file(alice)
    # Bob holds an asset named like one in the file: Alice's rows are not his to match.
    cash = next(a for a in _ok(bob.get("/api/assets")) if a["name"] == "Cash")
    _ok(bob.post("/api/positions", json={"asset_id": cash["id"], "amount": 5, "currency": "PLN"}), 201)

    def alice_state():
        return {
            "assets": _ok(alice.get("/api/assets")), "positions": _ok(alice.get("/api/positions")),
            "expenses": _ok(alice.get("/api/expenses")), "settings": _ok(alice.get("/api/settings")),
            "income": _ok(alice.get("/api/income/sources")),
        }

    alice_before, rows_before = alice_state(), _row_counts()
    _ok(_post_file(bob, "/api/wallet/import", f))
    changed = _changed_users(rows_before, _row_counts())
    bob_id = _ok(bob.get("/api/auth/me"))["user_id"].replace("-", "")
    alice_id = _ok(alice.get("/api/auth/me"))["user_id"].replace("-", "")
    assert changed == {bob_id}  # exactly one user's rows moved, and it is not Alice's
    assert alice_state() == alice_before
    # Bob's own Cash balance was a conflict for him, found only in his own wallet.
    prev = _ok(_post_file(bob, "/api/wallet/import/preview", f))
    assert {i["name"]: i["action"] for i in prev["items"] if i["section"] == "asset"}["Cash"] == "skip"
    assert alice_id != bob_id


def test_imported_values_are_encrypted_at_rest(users):
    _, bob = users
    f = _wallet(
        assets=[{**CASH, "name": "ZZ-Distinctive-Asset", "category": "ZZCat"}],
        expenses=[{"name": "ZZ-Distinctive-Expense", "amount": "123.45", "currency": "PLN",
                   "period": "monthly", "starts_on": "2026-01-01"}],
    )
    _ok(_post_file(bob, "/api/wallet/import", f))
    for table, col in (("assets", "name"), ("expenses", "name"), ("expenses", "amount"),
                       ("positions", "amount")):
        for (v,) in raw(f"SELECT {col} FROM {table}"):
            assert b"ZZ-Distinctive" not in bytes(v) and b"123.45" not in bytes(v)
            assert bytes(v)[:1] == b"\x01"


# --- rejected files: no partial writes ---------------------------------------------------


def _assert_rejected(bob, body: bytes, status: int):
    before = _row_counts()
    r = None
    for path in ("/api/wallet/import", "/api/wallet/import/preview"):
        r = bob.post(path, content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == status, (path, r.status_code, r.text[:300])
    assert _row_counts() == before
    return r


def test_rejects_garbage(users):
    _, bob = users
    _assert_rejected(bob, b"not json at all", 400)
    _assert_rejected(bob, b"\xff\xfe\x00bad bytes", 400)
    _assert_rejected(bob, b"[1, 2, 3]", 400)
    _assert_rejected(bob, b"", 400)
    _assert_rejected(bob, b"[" * 100000, 400)  # deeply nested, within the size cap


def test_rejects_wrong_format_and_versions(users):
    _, bob = users
    _assert_rejected(bob, json.dumps({**_wallet(), "format": "something-else"}).encode(), 422)
    for version in (2, 0, "1", 1.5, None, True, [1]):
        r = _assert_rejected(bob, json.dumps({**_wallet(), "version": version}).encode(), 422)
        assert "version" in r.text.lower()
    no_version = _wallet()
    del no_version["version"]
    _assert_rejected(bob, json.dumps(no_version).encode(), 422)


BAD_FILES = {
    "unknown top-level field": lambda: {**_wallet(), "extra": 1},
    "unknown asset field": lambda: _wallet(assets=[{**CASH, "id": 7}]),
    "unknown setting": lambda: _wallet(settings={"base_currency": "PLN", "nope": 1}),
    "bad base currency": lambda: _wallet(settings={"base_currency": "GBP"}),
    "bad timezone": lambda: _wallet(settings={"base_currency": "PLN", "timezone": "Mars/Base"}),
    "amount with too many decimals": lambda: _wallet(assets=[{**CASH, "amount": "1.1234567"}]),
    "negative amount": lambda: _wallet(assets=[{**CASH, "amount": "-1"}]),
    "amount in exponent form": lambda: _wallet(assets=[{**CASH, "amount": "1e3"}]),
    "amount is a bool": lambda: _wallet(assets=[{**CASH, "amount": True}]),
    "unknown kind": lambda: _wallet(assets=[{**CASH, "kind": "stocks"}]),
    "unsupported coin": lambda: _wallet(assets=[{**CASH, "kind": "crypto", "units": "DOGE"}]),
    "bad wrapper": lambda: _wallet(assets=[{**CASH, "wrapper": "ira"}]),
    "empty name": lambda: _wallet(assets=[{**CASH, "name": ""}]),
    "huge name": lambda: _wallet(assets=[{**CASH, "name": "x" * 500}]),
    "control characters": lambda: _wallet(assets=[{**CASH, "name": "a\x00b"}]),
    "one-off expense": lambda: _wallet(expenses=[{"name": "x", "amount": "1", "period": "once",
                                                  "starts_on": "2026-01-01"}]),
    "zero expense": lambda: _wallet(expenses=[{"name": "x", "amount": "0", "starts_on": "2026-01-01"}]),
    "expense ends before start": lambda: _wallet(expenses=[{
        "name": "x", "amount": "1", "starts_on": "2026-02-01", "ends_on": "2026-01-01"}]),
    "income params missing": lambda: _wallet(income_sources=[{
        "name": "J", "kind": "uop", "params": {}, "starts_on": "2026-01-01"}]),
    "unknown income param": lambda: _wallet(income_sources=[{
        "name": "J", "kind": "other", "starts_on": "2026-01-01",
        "params": {"net_monthly": "1", "evil": 1}}]),
    "future birth year": lambda: _wallet(settings={"base_currency": "PLN", "birth_year": 2999}),
    "fire out of range": lambda: _wallet(settings={"base_currency": "PLN", "fire": {"swr": 0.9}}),
}


@pytest.mark.parametrize("label", sorted(BAD_FILES))
def test_rejects_invalid_content(users, label):
    _, bob = users
    _assert_rejected(bob, json.dumps(BAD_FILES[label]()).encode(), 422)


def test_one_bad_item_among_good_ones_writes_nothing(users):
    _, bob = users
    body = _wallet(
        assets=[{**CASH}, {**CASH, "name": "Savings", "category": "Savings"},
                {**CASH, "name": "Broken", "kind": "crypto", "units": "NOPE"}],
        expenses=[{"name": "Fine", "amount": "10", "starts_on": "2026-01-01"}],
    )
    r = _assert_rejected(bob, json.dumps(body).encode(), 422)
    errors = r.json()["detail"]["errors"]
    assert errors and errors[0]["where"].startswith("assets.2")


def test_item_count_limits(users):
    from src.schemas.wallet import MAX_ASSETS, MAX_EXPENSES, MAX_INCOME_SOURCES

    _, bob = users
    exp = {"name": "x", "amount": "1", "starts_on": "2026-01-01"}
    src = {"name": "j", "kind": "other", "params": {"net_monthly": "1"}, "starts_on": "2026-01-01"}
    _assert_rejected(bob, json.dumps(_wallet(assets=[CASH] * (MAX_ASSETS + 1))).encode(), 422)
    _assert_rejected(bob, json.dumps(_wallet(expenses=[exp] * (MAX_EXPENSES + 1))).encode(), 422)
    _assert_rejected(bob, json.dumps(_wallet(income_sources=[src] * (MAX_INCOME_SOURCES + 1))).encode(), 422)
    # At the limit it is accepted.
    assert _post_file(bob, "/api/wallet/import/preview", _wallet(expenses=[exp] * MAX_EXPENSES)).status_code == 200


def test_oversized_file_is_refused(users):
    from src.schemas.wallet import MAX_FILE_BYTES

    _, bob = users
    body = json.dumps(_wallet()).encode() + b" " * (MAX_FILE_BYTES + 10)
    _assert_rejected(bob, body, 413)
    # Without a Content-Length (chunked) it is still stopped while reading.
    before = _row_counts()

    def chunks():
        for _ in range(0, MAX_FILE_BYTES + 10, 65536):
            yield b" " * 65536

    r = bob.post("/api/wallet/import", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert _row_counts() == before
    # Exactly at the limit is read (and then judged on its content).
    ok = json.dumps(_wallet()).encode()
    ok += b" " * (MAX_FILE_BYTES - len(ok))
    assert bob.post("/api/wallet/import/preview", content=ok).status_code == 200


def test_a_failure_while_writing_rolls_everything_back(db, monkeypatch):
    from src.schemas.wallet import WalletFile
    from src.services import wallet_io

    uid = make_user("ab" * 32)
    s = session_for(uid)
    try:
        wallet = WalletFile.model_validate(_wallet(
            assets=[{**CASH}, {**CASH, "name": "Second", "category": "Second"}],
            expenses=[{"name": "Fine", "amount": "10", "starts_on": "2026-01-01"}],
        ))
        real = wallet_io.compute_value
        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return real(*a, **kw)

        monkeypatch.setattr(wallet_io, "compute_value", flaky)
        before = _row_counts()
        with pytest.raises(RuntimeError):
            wallet_io.apply(s, uid, wallet)
    finally:
        s.close()
    assert _row_counts() == before
