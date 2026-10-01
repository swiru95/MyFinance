"""Two signed-in users on one database: neither can see, change or delete the
other's data through any endpoint family, and nothing one user's LLM job or PDF
is built from comes from the other's rows.

Alice and Bob are real bearer-token clients against a fake OIDC issuer (see
conftest.idp / fake_oidc.py). Another user's id is always a 404 - never a 403,
which would confirm that it exists.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid

import pytest

from src.routes import insights as insights_routes
from src.routes import reports as reports_routes
from src.scoping import open_session
from tests.conftest import make_client

ALL_ON = {"portfolio": True, "fire": True, "tax": True, "insights": True}

PROFILE_JSON = {
    "stated_tolerance": "medium", "capacity": "high", "revealed": "low", "mismatches": [],
    "priorities": ["Build an emergency fund"], "suggested_style": "balanced",
    "summary_md": "A cautious wallet.",
}
MARKDOWN = "## Summary\nA steady wallet.\n\n## What stood out\n- Cash.\n\n## Reading the numbers\nOK.\n"


# --- helpers ---------------------------------------------------------------

def _ok(r, status=200):
    assert r.status_code == status, f"{r.request.method} {r.request.url.path}: {r.status_code} {r.text}"
    return r.json() if r.content else None


def _populate(c, tag: str, amount: float) -> dict:
    """One of everything, named after `tag` so a leak is recognisable."""
    _ok(c.put("/api/settings", json={"base_currency": "PLN", "features": ALL_ON}))
    ids: dict = {"tag": tag, "amount": amount}
    asset = _ok(c.post("/api/assets", json={
        "name": f"{tag}Asset", "kind": "currency", "category": f"{tag}Cat", "profile": "safe",
    }), 201)
    ids["asset"] = asset["id"]
    pos = _ok(c.post("/api/positions", json={"asset_id": asset["id"], "amount": amount, "currency": "PLN"}), 201)
    ids["position"] = pos["id"]
    ids["expense"] = _ok(c.post("/api/expenses", json={
        "name": f"{tag}Rent", "amount": 1234, "currency": "PLN", "period": "monthly",
        "category": f"{tag}Housing", "starts_on": "2026-01-01",
    }), 201)["id"]
    src = _ok(c.post("/api/income/sources", json={
        "name": f"{tag}Job", "kind": "uop", "currency": "PLN",
        "params": {"gross_monthly": 10_000, "ppk_employee": 0, "ppk_employer": 0},
        "starts_on": "2026-01-01",
    }), 201)
    ids["source"] = src["id"]
    _ok(c.put(f"/api/income/sources/{src['id']}/entries/2026-03", json={"amount": 15_000 if tag == "Alice" else 20_000}))
    _ok(c.put("/api/monthly/2026-03", json={"income": amount, "actual_spent": 10, "currency": "PLN", "notes": f"{tag}Note"}))
    _ok(c.put("/api/fire/settings", json={"birth_year": 1990 if tag == "Alice" else 1980}))
    _ok(c.put("/api/insights/profile/answers", json={"goals": ["retire_early"] if tag == "Alice" else ["buy_home"]}))
    _ok(c.put("/api/insights/ladder/ppk_on", json={"state": "dismissed"}))
    return ids


@pytest.fixture
def world(two_users):
    alice, bob = two_users
    return alice, bob, _populate(alice, "Alice", 123456.0), _populate(bob, "Bob", 777.0)


@pytest.fixture
def llm(monkeypatch):
    """A configured model that records every prompt it is handed."""
    from src.services import llm as llm_service

    prompts: list[tuple[str, str]] = []

    def complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        prompts.append((system, user))
        if "profiling one" in system:
            return json.dumps(PROFILE_JSON)
        if "ranking a short list" in system:
            return json.dumps({"steps": []})
        return MARKDOWN

    monkeypatch.setattr(llm_service, "configured", lambda: True)
    monkeypatch.setattr(llm_service, "complete", complete)
    return prompts


def _stored_snapshots(client, model) -> list:
    """What the model was shown for each of this user's rows (not exposed by
    the API for reports, so read through a session scoped to them)."""
    db = open_session(uuid.UUID(client.get("/api/auth/me").json()["user_id"]))
    try:
        return [row.snapshot for row in db.query(model).all()]
    finally:
        db.close()


def _wait(c, path, timeout=10.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = c.get(path).json()
        if got["status"] in ("done", "failed"):
            return got
        time.sleep(0.02)
    raise AssertionError(f"{path} did not finish: {got}")


def _pdf_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(content)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, check=True).stdout.decode()


# --- every route is behind authentication --------------------------------------

OPEN_ROUTES = {("GET", "/api/health"), ("GET", "/api/auth/config")}


def _fill(path: str) -> str:
    for name, value in (
        ("asset_id", "1"), ("position_id", "1"), ("expense_id", "1"), ("source_id", "1"),
        ("insight_id", "1"), ("report_id", "1"), ("month", "2026-03"), ("year", "2026"),
        ("kind", "digest"), ("key", "ppk_on"), ("symbol", "XAU"),
    ):
        path = path.replace("{" + name + "}", value)
    assert "{" not in path, path
    return path


def test_every_api_route_rejects_a_request_without_a_token(idp):
    from src.main import app

    anonymous = make_client()
    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            if (method, path) in OPEN_ROUTES:
                continue
            r = anonymous.request(method, _fill(path))
            assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a token"
            checked += 1
    assert checked >= 60


# --- assets ----------------------------------------------------------------------

def test_assets_are_listed_per_user(world):
    alice, bob, A, B = world
    names_a = {a["name"] for a in alice.get("/api/assets").json()}
    names_b = {a["name"] for a in bob.get("/api/assets").json()}
    assert "AliceAsset" in names_a and "BobAsset" not in names_a
    assert "BobAsset" in names_b and "AliceAsset" not in names_b


def test_another_users_asset_id_is_404_for_every_verb(world):
    alice, bob, A, B = world
    aid = A["asset"]
    assert bob.put(f"/api/assets/{aid}", json={"name": "pwned"}).status_code == 404
    assert bob.delete(f"/api/assets/{aid}").status_code == 404
    assert bob.post(f"/api/assets/{aid}/archive").status_code == 404
    assert bob.post(f"/api/assets/{aid}/unarchive").status_code == 404
    # Untouched.
    mine = {a["id"]: a for a in alice.get("/api/assets").json()}
    assert mine[aid]["name"] == "AliceAsset" and mine[aid]["archived_at"] is None
    assert len(alice.get("/api/positions").json()) == 1


def test_a_user_can_still_change_their_own_asset(world):
    alice, bob, A, B = world
    assert alice.put(f"/api/assets/{A['asset']}", json={"name": "Renamed"}).status_code == 200
    assert "Renamed" not in {a["name"] for a in bob.get("/api/assets").json()}


# --- positions -------------------------------------------------------------------

def test_positions_are_listed_per_user(world):
    alice, bob, A, B = world
    assert [p["amount"] for p in alice.get("/api/positions").json()] == [A["amount"]]
    assert [p["amount"] for p in bob.get("/api/positions").json()] == [B["amount"]]


def test_another_users_position_is_404_for_every_verb(world):
    alice, bob, A, B = world
    pid = A["position"]
    assert bob.get(f"/api/positions/{pid}").status_code == 404
    assert bob.get(f"/api/positions/{pid}/history").status_code == 404
    assert bob.put(f"/api/positions/{pid}", json={"amount": 1, "currency": "PLN"}).status_code == 404
    assert bob.delete(f"/api/positions/{pid}").status_code == 404
    got = alice.get(f"/api/positions/{pid}").json()
    assert got["amount"] == A["amount"]
    assert len(alice.get(f"/api/positions/{pid}/history").json()) == 1


def test_a_position_cannot_be_recorded_against_another_users_asset(world):
    alice, bob, A, B = world
    r = bob.post("/api/positions", json={"asset_id": A["asset"], "amount": 1, "currency": "PLN"})
    assert r.status_code == 404
    assert len(alice.get("/api/positions").json()) == 1


def test_growth_statistics_summary_and_prices_are_per_user(world):
    alice, bob, A, B = world
    assert alice.get("/api/summary").json()["total_value"] == A["amount"]
    assert bob.get("/api/summary").json()["total_value"] == B["amount"]
    assert alice.get("/api/statistics/allocation").json()["total"] == A["amount"]
    assert bob.get("/api/statistics/allocation").json()["total"] == B["amount"]
    assert "AliceCat" not in json.dumps(bob.get("/api/statistics/allocation").json())
    assert "AliceAsset" not in json.dumps(bob.get("/api/statistics/value-over-time").json())
    ga, gb = alice.get("/api/positions/growth").json(), bob.get("/api/positions/growth").json()
    assert [a["asset_id"] for a in ga["assets"]] == [A["asset"]] and ga["total"]["value"] == A["amount"]
    assert [a["asset_id"] for a in gb["assets"]] == [B["asset"]] and gb["total"]["value"] == B["amount"]
    # Prices are public data, but which symbols are fetched follows what *you* hold.
    assert alice.get("/api/prices").status_code == 200


def test_deleting_a_position_history_leaves_the_other_users_alone(world):
    alice, bob, A, B = world
    assert bob.delete(f"/api/positions/{B['position']}").status_code == 204
    assert [p["amount"] for p in alice.get("/api/positions").json()] == [A["amount"]]
    assert bob.get("/api/positions").json() == []


# --- expenses --------------------------------------------------------------------

def test_expenses_are_listed_per_user(world):
    alice, bob, A, B = world
    assert [e["name"] for e in alice.get("/api/expenses").json()] == ["AliceRent"]
    assert [e["name"] for e in bob.get("/api/expenses").json()] == ["BobRent"]
    assert "AliceHousing" not in json.dumps(bob.get("/api/expenses/summary").json())


def test_another_users_expense_is_404_for_every_verb(world):
    alice, bob, A, B = world
    eid = A["expense"]
    body = {"name": "x", "amount": 1, "currency": "PLN", "period": "monthly", "starts_on": "2026-01-01"}
    assert bob.get(f"/api/expenses/{eid}").status_code == 404
    assert bob.put(f"/api/expenses/{eid}", json=body).status_code == 404
    assert bob.delete(f"/api/expenses/{eid}").status_code == 404
    assert alice.get(f"/api/expenses/{eid}").json()["name"] == "AliceRent"


# --- income ----------------------------------------------------------------------

def test_income_sources_are_listed_per_user(world):
    alice, bob, A, B = world
    assert [s["name"] for s in alice.get("/api/income/sources").json()] == ["AliceJob"]
    assert [s["name"] for s in bob.get("/api/income/sources").json()] == ["BobJob"]


def test_another_users_income_source_and_entries_are_404(world):
    alice, bob, A, B = world
    sid = A["source"]
    body = {"name": "x", "kind": "uop", "currency": "PLN", "params": {"gross_monthly": 1}, "starts_on": "2026-01-01"}
    assert bob.put(f"/api/income/sources/{sid}", json=body).status_code == 404
    assert bob.delete(f"/api/income/sources/{sid}").status_code == 404
    assert bob.get(f"/api/income/sources/{sid}/year/2026").status_code == 404
    assert bob.put(f"/api/income/sources/{sid}/entries/2026-03", json={"amount": 1}).status_code == 404
    assert bob.put(f"/api/income/sources/{sid}/entries/2026-09", json={"amount": 1}).status_code == 404
    assert bob.delete(f"/api/income/sources/{sid}/entries/2026-03").status_code == 404
    year = alice.get(f"/api/income/sources/{sid}/year/2026").json()
    march = next(m for m in year["months"] if m["month"] == "2026-03")
    assert march["has_entry"] is True


def test_income_summary_is_per_user(world):
    alice, bob, A, B = world
    ja = alice.get("/api/income/summary?year=2026").json()
    jb = bob.get("/api/income/summary?year=2026").json()
    march = lambda j: next(m for m in j["months"] if m["month"] == "2026-03")["gross"]  # noqa: E731
    assert (march(ja), march(jb)) == (15_000.0, 20_000.0)


def test_a_new_users_view_of_everything_is_empty(idp):
    carol = make_client(idp.token("sub-carol"))
    assert carol.get("/api/positions").json() == []
    assert carol.get("/api/expenses").json() == []
    assert carol.get("/api/income/sources").json() == []
    assert carol.get("/api/reports").json() == []
    assert carol.get("/api/insights").json() == []
    assert carol.get("/api/summary").json()["total_value"] == 0
    summary = carol.get("/api/income/summary?year=2026").json()
    assert all(m["gross"] == 0 and m["net"] == 0 for m in summary["months"])


# --- monthly budget ----------------------------------------------------------------

def test_monthly_records_are_per_user_even_for_the_same_month(world):
    alice, bob, A, B = world
    ma, mb = alice.get("/api/monthly/2026-03").json(), bob.get("/api/monthly/2026-03").json()
    assert (ma["income"], ma["notes"]) == (A["amount"], "AliceNote")
    assert (mb["income"], mb["notes"]) == (B["amount"], "BobNote")
    # Writing one leaves the other.
    _ok(bob.put("/api/monthly/2026-03", json={"income": 1, "actual_spent": 1, "currency": "PLN"}))
    assert alice.get("/api/monthly/2026-03").json()["income"] == A["amount"]
    _ok(bob.patch("/api/monthly/2026-03", json={"notes": "bob-patched"}))
    assert alice.get("/api/monthly/2026-03").json()["notes"] == "AliceNote"
    # Deleting one leaves the other.
    assert bob.delete("/api/monthly/2026-03").status_code == 204
    assert alice.get("/api/monthly/2026-03").json()["notes"] == "AliceNote"
    assert "AliceNote" not in json.dumps(bob.get("/api/monthly").json())
    assert "AliceHousing" not in json.dumps(bob.get("/api/monthly/analytics").json())


def test_the_month_checklist_only_lists_the_callers_commitments(world):
    alice, bob, A, B = world
    names_a = {c["name"] for c in alice.get("/api/monthly/2026-03/commitments").json()}
    names_b = {c["name"] for c in bob.get("/api/monthly/2026-03/commitments").json()}
    assert names_a == {"AliceRent"} and names_b == {"BobRent"}


def test_a_checklist_cannot_reference_another_users_expense(world):
    alice, bob, A, B = world
    r = bob.patch("/api/monthly/2026-04", json={
        "commitments": [{"expense_id": A["expense"], "amount": 1, "paid": True}],
    })
    # Indistinguishable from an id that does not exist, which this API already
    # answers 422 for (the id is in the body, not the path).
    assert r.status_code == 422
    assert "AliceRent" not in r.text


# --- settings, fire, profile, ladder -----------------------------------------------

def test_settings_are_per_user(world):
    alice, bob, A, B = world
    _ok(alice.put("/api/settings", json={"base_currency": "EUR", "timezone": "Europe/London", "features": ALL_ON}))
    sa, sb = alice.get("/api/settings").json(), bob.get("/api/settings").json()
    assert (sa["base_currency"], sa["timezone"]) == ("EUR", "Europe/London")
    assert (sb["base_currency"], sb["timezone"]) == ("PLN", "Europe/Warsaw")
    _ok(bob.put("/api/settings", json={"base_currency": "USD", "features": {**ALL_ON, "tax": False}}))
    assert alice.get("/api/settings").json()["base_currency"] == "EUR"
    assert alice.get("/api/settings").json()["features"]["tax"] is True
    assert alice.get("/api/summary").json()["base_currency"] == "EUR"
    assert bob.get("/api/summary").json()["base_currency"] == "USD"


def test_terms_acceptance_belongs_to_the_user(idp):
    alice = make_client(idp.token("sub-alice"))
    bob = make_client(idp.token("sub-bob"))
    assert alice.get("/api/settings").json()["terms"]["accepted_version"] is None
    terms = _ok(alice.post("/api/settings/terms/accept", json={"version": 1}))["terms"]
    assert terms["accepted_version"] == 1 and terms["accepted_at"]
    assert bob.get("/api/settings").json()["terms"] == {
        "current_version": 1, "accepted_version": None, "accepted_at": None,
    }
    assert alice.get("/api/settings").json()["terms"] == terms
    # Stored on the user row, not as a setting.
    from sqlalchemy import select

    from src.models.settings import Setting
    from tests.conftest import system_session

    db = system_session()
    try:
        assert db.execute(select(Setting).where(Setting.key == "terms_accepted")).first() is None
    finally:
        db.close()


def test_fire_profile_answers_and_ladder_feedback_are_per_user(world):
    alice, bob, A, B = world
    assert alice.get("/api/fire/settings").json()["birth_year"] == 1990
    assert bob.get("/api/fire/settings").json()["birth_year"] == 1980
    assert alice.get("/api/insights/profile/answers").json()["goals"] == ["retire_early"]
    assert bob.get("/api/insights/profile/answers").json()["goals"] == ["buy_home"]
    _ok(bob.put("/api/insights/ladder/ppk_on", json={"state": "done"}))
    rung = lambda c: next(r for r in c.get("/api/insights/ladder").json()["rungs"] if r["key"] == "ppk_on")  # noqa: E731
    assert rung(alice)["feedback"]["state"] == "dismissed"
    assert rung(bob)["feedback"]["state"] == "done"
    assert alice.get("/api/fire").status_code == 200


# --- insights ------------------------------------------------------------------

def test_insights_are_listed_and_fetched_per_user(world, llm):
    alice, bob, A, B = world
    ia = _ok(alice.post("/api/insights/digest", json={"language": "en", "period": "2026-03"}), 202)
    assert _wait(alice, f"/api/insights/item/{ia['id']}")["status"] == "done"

    assert bob.get(f"/api/insights/item/{ia['id']}").status_code == 404
    assert bob.delete(f"/api/insights/item/{ia['id']}").status_code == 404
    assert bob.get("/api/insights").json() == []
    assert bob.get("/api/insights/digest/latest?language=en").status_code == 404
    assert bob.get("/api/insights/digest/latest?language=en&period=2026-03").status_code == 404
    # Alice's is untouched and still hers.
    assert alice.get(f"/api/insights/item/{ia['id']}").status_code == 200
    assert [i["id"] for i in alice.get("/api/insights").json()] == [ia["id"]]
    assert alice.get("/api/insights/digest/latest?language=en").json()["id"] == ia["id"]

    ib = _ok(bob.post("/api/insights/digest", json={"language": "en", "period": "2026-03"}), 202)
    assert _wait(bob, f"/api/insights/item/{ib['id']}")["status"] == "done"
    assert alice.get(f"/api/insights/item/{ib['id']}").status_code == 404
    assert bob.delete(f"/api/insights/item/{ib['id']}").status_code == 204
    assert alice.get(f"/api/insights/item/{ia['id']}").status_code == 200


def test_every_insight_kind_is_built_only_from_the_callers_data(world, llm):
    alice, bob, A, B = world
    for kind, body in (
        ("profile", {"language": "en"}),
        ("digest", {"language": "en", "period": "2026-03"}),
        ("next_steps", {"language": "en"}),
        ("wallet_pdf", {"language": "en", "period": "all"}),
    ):
        for client in (alice, bob):
            row = _ok(client.post(f"/api/insights/{kind}", json=body), 202)
            got = _wait(client, f"/api/insights/item/{row['id']}")
            assert got["status"] == "done", (kind, got)

    alice_text = "\n".join(s + u for s, u in llm)
    assert llm, "the model was never called"
    # Walk the prompts per user: split by who asked is not recorded, so check the
    # stored snapshots - exactly what each job was shown - row by row.
    for client, own, other in ((alice, "Alice", "Bob"), (bob, "Bob", "Alice")):
        for item in client.get("/api/insights").json():
            full = client.get(f"/api/insights/item/{item['id']}").json()
            blob = json.dumps(full["snapshot"]) + full["content"] + json.dumps(full["data"])
            assert other not in blob, (item["kind"], other)
    assert "AliceAsset" in alice_text or "AliceCat" in alice_text


def test_prompts_sent_to_the_model_contain_no_identity(world, llm):
    alice, bob, A, B = world
    for kind, body in (("profile", {"language": "en"}), ("digest", {"language": "en", "period": "2026-03"}),
                       ("next_steps", {"language": "en"}), ("wallet_pdf", {"language": "en", "period": "all"})):
        row = _ok(alice.post(f"/api/insights/{kind}", json=body), 202)
        assert _wait(alice, f"/api/insights/item/{row['id']}")["status"] == "done"
    row = _ok(alice.post("/api/reports", json={"style": "balanced", "language": "en"}), 202)
    assert _wait(alice, f"/api/reports/{row['id']}")["status"] == "done"
    everything = "\n".join(s + "\n" + u for s, u in llm).lower()
    for needle in ("sub-alice", "alice example", "alice@example.test", "example.test"):
        assert needle not in everything


# --- reports -------------------------------------------------------------------

def test_reports_are_listed_and_fetched_per_user(world, llm):
    alice, bob, A, B = world
    from src.models.report import Report

    ra = _ok(alice.post("/api/reports", json={"style": "balanced", "language": "en"}), 202)
    assert _wait(alice, f"/api/reports/{ra['id']}")["status"] == "done"
    assert bob.get(f"/api/reports/{ra['id']}").status_code == 404
    assert bob.delete(f"/api/reports/{ra['id']}").status_code == 404
    assert bob.get("/api/reports").json() == []
    assert [r["id"] for r in alice.get("/api/reports").json()] == [ra["id"]]
    assert "Bob" not in json.dumps(_stored_snapshots(alice, Report))

    rb = _ok(bob.post("/api/reports", json={"style": "safe", "language": "en"}), 202)
    assert _wait(bob, f"/api/reports/{rb['id']}")["status"] == "done"
    assert "Alice" not in json.dumps(_stored_snapshots(bob, Report))
    assert alice.get(f"/api/reports/{rb['id']}").status_code == 404
    assert alice.get(f"/api/reports/{ra['id']}").status_code == 200


def _user_id(client) -> uuid.UUID:
    return uuid.UUID(client.get("/api/auth/me").json()["user_id"])


def test_a_queued_job_runs_as_the_user_who_queued_it_and_only_that_user(world, llm):
    """The job closure carries the user id; handing it someone else's row id
    finds no row to work on."""
    alice, bob, A, B = world
    from src.models.insight import Insight
    from src.models.report import Report

    ra = _ok(alice.post("/api/reports", json={"style": "balanced", "language": "en"}), 202)
    _wait(alice, f"/api/reports/{ra['id']}")
    ia = _ok(alice.post("/api/insights/digest", json={"language": "en", "period": "2026-03"}), 202)
    _wait(alice, f"/api/insights/item/{ia['id']}")

    # Put both of Alice's rows back to "pending", as if freshly queued.
    db = open_session(_user_id(alice))
    try:
        for model, row_id in ((Report, ra["id"]), (Insight, ia["id"])):
            row = db.query(model).filter(model.id == row_id).one()
            row.status, row.content = "pending", ""
        db.commit()
    finally:
        db.close()

    calls_before = len(llm)
    reports_routes._generate(_user_id(bob), ra["id"])
    insights_routes._generate(_user_id(bob), ia["id"])
    assert len(llm) == calls_before, "Bob's job reached the model with Alice's row"
    assert alice.get(f"/api/reports/{ra['id']}").json()["status"] == "pending"
    assert alice.get(f"/api/insights/item/{ia['id']}").json()["status"] == "pending"

    # The same jobs run as Alice do the work.
    reports_routes._generate(_user_id(alice), ra["id"])
    insights_routes._generate(_user_id(alice), ia["id"])
    assert alice.get(f"/api/reports/{ra['id']}").json()["status"] == "done"
    assert alice.get(f"/api/insights/item/{ia['id']}").json()["status"] == "done"


# --- PDF -----------------------------------------------------------------------

def test_the_pdf_contains_only_the_callers_holdings(world):
    alice, bob, A, B = world
    ta = _pdf_text(_ok_bytes(alice.get("/api/reports/pdf?period=all&language=en")))
    tb = _pdf_text(_ok_bytes(bob.get("/api/reports/pdf?period=all&language=en")))
    assert "AliceAsset" in ta and "BobAsset" not in ta
    assert "BobAsset" in tb and "AliceAsset" not in tb
    assert "123,456" in ta.replace(" ", ",") or "123 456" in ta or "123456" in ta
    # Nothing identifying the person is printed.
    for text in (ta, tb):
        for needle in ("sub-alice", "sub-bob", "Example", "example.test"):
            assert needle not in text


def _ok_bytes(r) -> bytes:
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")
    return r.content


def test_another_users_ai_commentary_cannot_be_embedded_in_a_pdf(world, llm):
    alice, bob, A, B = world
    row = _ok(alice.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"}), 202)
    assert _wait(alice, f"/api/insights/item/{row['id']}")["status"] == "done"

    r = bob.get(f"/api/reports/pdf?period=all&language=en&ai_insight_id={row['id']}")
    assert r.status_code == 404
    # Alice can, and it is built from her own stored snapshot.
    mine = alice.get(f"/api/reports/pdf?period=all&language=en&ai_insight_id={row['id']}")
    assert mine.status_code == 200
    assert "AliceAsset" in _pdf_text(mine.content)
