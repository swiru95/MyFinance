"""Insight jobs end to end: POST -> shared LLM queue -> poll to done, with
services.llm.complete monkeypatched so no test ever reaches a real model.
"""
import json
import time

DIGEST_MD = (
    "## This month\nNothing much happened.\n\n"
    "## What changed\nNo prior data to compare.\n\n"
    "## One thing to focus on\nStart tracking your spending.\n"
)

PROFILE_JSON = {
    "stated_tolerance": "medium",
    "capacity": "high",
    "revealed": "low",
    "mismatches": [],
    "priorities": ["Build an emergency fund"],
    "suggested_style": "balanced",
    "summary_md": "This wallet mixes stable income with a cautious allocation.",
}


def _poll(client, insight_id, timeout=5.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = client.get(f"/api/insights/item/{insight_id}").json()
        if got["status"] in ("done", "failed"):
            return got
        time.sleep(0.01)
    raise AssertionError(f"insight {insight_id} did not finish in time: {got}")


def _unconfigured_llm(monkeypatch):
    """Baseline: no model configured (conftest already strips the env vars)."""
    from src.services import llm

    return llm


def _configured_llm(monkeypatch):
    from src.services import llm

    monkeypatch.setattr(llm, "configured", lambda: True)
    return llm


# --- status / 503 -----------------------------------------------------

def test_status_reports_unconfigured_by_default(client):
    body = client.get("/api/insights/status").json()
    assert body == {"configured": False, "model": "Thinker", "translator": "Bielik"}


def test_post_returns_503_when_not_configured(client):
    for kind in ("profile", "digest", "next_steps"):
        r = client.post(f"/api/insights/{kind}", json={"language": "en"})
        assert r.status_code == 503, (kind, r.text)


def test_unknown_kind_is_404(client):
    r = client.post("/api/insights/nonsense", json={"language": "en"})
    assert r.status_code == 404


# --- profile answers ----------------------------------------------------

def test_profile_answers_default_before_anything_saved(client):
    body = client.get("/api/insights/profile/answers").json()
    assert body["goals"] == []
    assert body["horizon_years"] is None


def test_profile_answers_round_trip(client):
    payload = {
        "goals": ["retire_early", "buy_home"],
        "horizon_years": 15,
        "household": "couple",
        "dependents": 1,
        "income_stability_feel": "medium",
        "drawdown_reaction": "hold",
        "loss_tolerance_pct": 20,
        "fire_interest": "planning",
        "experience": "intermediate",
    }
    put = client.put("/api/insights/profile/answers", json=payload)
    assert put.status_code == 200, put.text
    got = client.get("/api/insights/profile/answers").json()
    for k, v in payload.items():
        assert got[k] == v


# --- ladder ---------------------------------------------------------------

def test_ladder_endpoint_lists_nine_rungs(client):
    body = client.get("/api/insights/ladder").json()
    assert len(body["rungs"]) == 9
    assert {r["key"] for r in body["rungs"]} == {
        "starter_buffer", "envelope_covered", "emergency_fund", "ppk_on",
        "ikze_used", "ike_used", "fire_configured", "savings_rate_on_track",
        "data_fresh",
    }


def test_ladder_put_records_feedback(client):
    r = client.put("/api/insights/ladder/ppk_on", json={"state": "dismissed"})
    assert r.status_code == 200, r.text
    rung = next(x for x in r.json()["rungs"] if x["key"] == "ppk_on")
    assert rung["feedback"]["state"] == "dismissed"


def test_ladder_put_unknown_key_is_404(client):
    r = client.put("/api/insights/ladder/not_a_real_key", json={"state": "done"})
    assert r.status_code == 404


def test_ladder_put_rejects_unknown_state(client):
    r = client.put("/api/insights/ladder/ppk_on", json={"state": "maybe"})
    assert r.status_code == 422


# --- profile job ------------------------------------------------------

def test_profile_job_completes(client, monkeypatch):
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        assert response_format is not None
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "en"})
    assert r.status_code == 202, r.text
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["kind"] == "profile"
    assert got["data"]["suggested_style"] == "balanced"
    assert "This wallet mixes" in got["content_en"]
    assert got["content"] == got["content_en"]  # language=en, no translation
    assert got["model"] == "Thinker"


def test_profile_retries_without_response_format_when_rejected(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    calls: list = []

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        calls.append(response_format)
        if response_format is not None:
            # A 4xx rejection - e.g. the server does not understand
            # response_format - is the one case _complete_json retries.
            raise llm.LLMBadRequest("this server does not support response_format")
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert len(calls) == 2
    assert calls[0] is not None
    assert calls[1] is None


def test_profile_does_not_retry_a_timeout_or_connection_failure(client, monkeypatch):
    """A plain LLMUnavailable (timeout, connection failure, 5xx) is not the
    same as a 4xx rejection and must not be retried - retrying would
    silently double an already-minutes-long wait for the same failure."""
    llm = _configured_llm(monkeypatch)
    calls: list = []

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        calls.append(response_format)
        raise llm.LLMUnavailable("timed out waiting for the model server")

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "failed", got
    assert len(calls) == 1


def test_profile_fails_cleanly_on_malformed_json(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "not json at all")

    r = client.post("/api/insights/profile", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "failed"
    assert got["error"]


def test_profile_en_never_calls_translator(client, monkeypatch):
    """The translate model is only ever needed for a pl job - an en job
    should never reach it, for the Markdown *or* the data translation."""
    llm = _configured_llm(monkeypatch)
    calls: list[str] = []

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        calls.append(model)
        if model == "Thinker":
            return json.dumps(PROFILE_JSON)
        raise AssertionError(f"translator should not run for an en job: {model}")

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is None
    assert calls and all(m == "Thinker" for m in calls)


def test_profile_pl_produces_data_localized(client, monkeypatch):
    """The structured data -> data_localized pass now sends a flat JSON
    array of leaf strings (see services/insights.py:_flatten_strings) rather
    than an object mirroring `data`'s own keys, so there are no keys for a
    model to mistranslate or drop."""
    llm = _configured_llm(monkeypatch)
    translated_summary = "To portfolio laczy stabilny dochod z ostroznym rozlokowaniem."
    translated_priority = "Zbuduj fundusz awaryjny"

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            assert response_format is not None
            return json.dumps(PROFILE_JSON)
        if model == "Bielik":
            if response_format is None:
                # The Markdown content_en -> content translation pass.
                return "## Podsumowanie\nPrzetlumaczony tekst raportu."
            # The structured data -> data_localized translation pass: a flat
            # array of leaf strings, in the order _flatten_strings visits
            # summary_md, then priorities[], then mismatches[] (empty here).
            leaves = json.loads(user)
            assert leaves == [PROFILE_JSON["summary_md"], PROFILE_JSON["priorities"][0]]
            return json.dumps([translated_summary, translated_priority])
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is not None
    assert got["data_localized"]["summary_md"] == translated_summary
    assert got["data_localized"]["priorities"] == [translated_priority]
    # Enums and keys are copied through untouched, not re-translated.
    assert got["data_localized"]["stated_tolerance"] == got["data"]["stated_tolerance"]
    assert got["data_localized"]["capacity"] == got["data"]["capacity"]
    assert got["data_localized"]["revealed"] == got["data"]["revealed"]
    assert got["data_localized"]["suggested_style"] == got["data"]["suggested_style"]
    # The English data is untouched by the translation.
    assert got["data"]["summary_md"] == PROFILE_JSON["summary_md"]
    # No leaf failed, so there is nothing to note.
    assert got["error"] == ""


def test_profile_pl_translation_falls_back_per_leaf_on_bad_shape(client, monkeypatch):
    """The bulk array translation coming back the wrong length must not
    throw away the whole translation - localize_data falls back to
    translating each string on its own instead."""
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            return json.dumps(PROFILE_JSON)
        if model == "Bielik":
            if response_format is not None:
                # Bulk array call: wrong length for the 2 leaves sent -
                # forces the per-leaf fallback.
                return json.dumps(["only one string"])
            if user in (PROFILE_JSON["summary_md"], PROFILE_JSON["priorities"][0]):
                # A per-leaf fallback call - answer deterministically so each
                # leaf's translation is distinguishable in the assertions.
                return f"[PL] {user}"
            # The Markdown content_en -> content translation pass.
            return "## Podsumowanie\nPrzetlumaczony tekst raportu."
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is not None
    assert got["data_localized"]["summary_md"] == f"[PL] {PROFILE_JSON['summary_md']}"
    assert got["data_localized"]["priorities"] == [f"[PL] {PROFILE_JSON['priorities'][0]}"]
    assert got["content"]  # the Markdown translation still went through
    # Every leaf translated fine via the fallback - nothing to note.
    assert got["error"] == ""


def test_profile_pl_translation_unavailable_when_everything_fails(client, monkeypatch):
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            return json.dumps(PROFILE_JSON)
        if model == "Bielik":
            if response_format is None and user not in (
                PROFILE_JSON["summary_md"], PROFILE_JSON["priorities"][0],
            ):
                # The Markdown content_en -> content translation pass still
                # succeeds independently of the data translation below.
                return "## Podsumowanie\nPrzetlumaczony tekst raportu."
            # Both the bulk array call and every per-leaf fallback fail.
            raise llm.LLMUnavailable("model server unreachable")
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    # The job still finishes - a bad data translation degrades to a note in
    # the UI, it must not fail a job whose Markdown content translated fine.
    assert got["status"] == "done", got
    assert got["data_localized"] is None
    assert "Data translation unavailable" in got["error"]
    assert got["content"]  # the Markdown translation still went through


# --- digest job -------------------------------------------------------

def test_digest_job_defaults_period_and_completes(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: DIGEST_MD)

    r = client.post("/api/insights/digest", json={"language": "en"})
    assert r.status_code == 202, r.text
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["period"] != ""
    assert "## This month" in got["content"]
    assert got["content"] == got["content_en"]


def test_digest_translates_to_polish(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    polish_md = (
        "## Ten miesiac\nNic sie nie wydarzylo.\n\n"
        "## Co sie zmienilo\nBrak wczesniejszych danych.\n\n"
        "## Jedna rzecz do zrobienia\nZacznij sledzic wydatki."
    )

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        return polish_md if model == "Bielik" else DIGEST_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/digest", json={"language": "pl", "period": "2025-06"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["period"] == "2025-06"
    assert got["translator"] == "Bielik"
    assert "Ten miesiac" in got["content"]
    assert "This month" in got["content_en"]


def test_digest_latest_and_list_endpoints(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: DIGEST_MD)

    r = client.post("/api/insights/digest", json={"language": "en"})
    insight_id = r.json()["id"]
    _poll(client, insight_id)

    latest = client.get("/api/insights/digest/latest?language=en")
    assert latest.status_code == 200
    assert latest.json()["id"] == insight_id

    missing = client.get("/api/insights/digest/latest?language=pl")
    assert missing.status_code == 404

    listing = client.get("/api/insights").json()
    assert any(row["id"] == insight_id for row in listing)

    delete = client.delete(f"/api/insights/item/{insight_id}")
    assert delete.status_code == 204
    assert client.get(f"/api/insights/item/{insight_id}").status_code == 404


# --- next_steps job -----------------------------------------------------

def test_next_steps_drops_unknown_key(client, monkeypatch):
    llm = _configured_llm(monkeypatch)

    steps_json = {
        "steps": [
            {
                "key": "fire_configured",
                "title": "Set your FIRE target",
                "why_md": "Planning needs a birth year and a target age to work from.",
            },
            {
                "key": "not_a_real_rung",
                "title": "Made up",
                "why_md": "This key does not exist on the ladder.",
            },
        ],
    }

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        assert response_format is not None
        return json.dumps(steps_json)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/next_steps", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    kept_keys = [s["key"] for s in got["data"]["steps"]]
    assert kept_keys == ["fire_configured"]
    assert any("not_a_real_rung" in u for u in got["ungrounded"])


def test_next_steps_pl_produces_data_localized(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    steps_json = {
        "steps": [
            {
                "key": "fire_configured",
                "title": "Set your FIRE target",
                "why_md": "Planning needs a birth year and a target age to work from.",
            },
        ],
    }
    translated_title = "Ustaw cel FIRE"
    translated_why = "Planowanie wymaga roku urodzenia i docelowego wieku."

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            assert response_format is not None
            return json.dumps(steps_json)
        if model == "Bielik":
            if response_format is None:
                return "## Kolejny krok\nUstaw cel FIRE."
            # A flat array of leaf strings - title then why_md, the order
            # _flatten_strings visits _next_steps_translatable's steps[0].
            leaves = json.loads(user)
            assert leaves == [
                "Set your FIRE target",
                "Planning needs a birth year and a target age to work from.",
            ]
            return json.dumps([translated_title, translated_why])
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/next_steps", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is not None
    loc_step = got["data_localized"]["steps"][0]
    assert loc_step["title"] == translated_title
    assert loc_step["why_md"] == translated_why
    # key is not prose - copied through untouched, never re-translated.
    assert loc_step["key"] == "fire_configured"
    assert got["data"]["steps"][0]["title"] == "Set your FIRE target"


def test_next_steps_en_never_calls_translator(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    steps_json = {
        "steps": [
            {
                "key": "fire_configured",
                "title": "Set your FIRE target",
                "why_md": "Planning needs a birth year and a target age to work from.",
            },
        ],
    }
    calls: list[str] = []

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        calls.append(model)
        if model == "Thinker":
            return json.dumps(steps_json)
        raise AssertionError(f"translator should not run for an en job: {model}")

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/next_steps", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is None
    assert calls and all(m == "Thinker" for m in calls)


def test_ladder_feedback_is_also_keyed_at_the_top(client):
    """The next-steps cards read ladder.feedback[key]; it must exist."""
    body = client.put("/api/insights/ladder/ppk_on", json={"state": "later"}).json()
    assert body["feedback"]["ppk_on"]["state"] == "later"
    assert client.get("/api/insights/ladder").json()["feedback"]["ppk_on"]["state"] == "later"


def test_failed_digest_polish_translation_ends_done_with_english_and_a_note(client, monkeypatch):
    """Same fallback as the wallet report (routes/reports.py): a translation
    hiccup must not throw away an already-finished English digest."""
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Bielik":
            raise llm.LLMUnavailable("model server unreachable")
        return DIGEST_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/digest", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert "## This month" in got["content"]  # the English digest, not lost
    assert got["translator"] == ""
    assert "Could not translate to Polish" in got["error"]


# --- default digest period -------------------------------------------------

def test_default_digest_period_is_the_current_month(db):
    from src.routes.helpers import today_in
    from src.services import insights
    from src.services.budget import month_key

    assert insights._default_digest_period(db) == month_key(today_in(db))


def test_digest_job_without_period_uses_current_month(client, db, monkeypatch):
    from src.routes.helpers import today_in
    from src.services.budget import month_key

    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: DIGEST_MD)

    r = client.post("/api/insights/digest", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["period"] == month_key(today_in(db))


# --- digest snapshot: an unrecorded month is "not recorded", not 0/100% ----

def test_digest_snapshot_marks_unrecorded_month_as_not_recorded(db):
    """No MonthlyRecord for the month must reach the prompt as "not
    recorded" - never as a typed spend of 0.00 and a 100% savings rate, the
    bug behind the production digest that opened on an unrecorded month."""
    from src.routes.helpers import today_in
    from src.services import insights
    from src.services.budget import month_key

    period = month_key(today_in(db))
    snap = insights.build_digest_snapshot(db, period)

    assert snap["recorded"] is False
    assert snap["typed_spend"] is None
    assert snap["savings_rate"] is None

    text = insights.render_digest_snapshot(snap)
    assert "not recorded" in text
    assert "Savings rate this month: not available" in text
    assert "100%" not in text
    assert "0.00" not in text.split("## Spending")[1].split("## Portfolio")[0]


def test_digest_snapshot_recorded_month_keeps_its_real_figures(db):
    """A month that *does* have a MonthlyRecord must not be swept into the
    same "not recorded" treatment - only a genuinely missing record is."""
    from src.models.monthly import MonthlyRecord
    from src.routes.helpers import today_in
    from src.services import insights
    from src.services.budget import month_key

    period = month_key(today_in(db))
    db.add(MonthlyRecord(month=period, income=1000, actual_spent=400, currency="PLN", notes=""))
    db.commit()

    snap = insights.build_digest_snapshot(db, period)
    assert snap["recorded"] is True
    assert snap["typed_spend"] == 400.0
    assert snap["savings_rate"] is not None


def test_digest_snapshot_carries_committed_and_holdings_summary(db):
    from src.routes.helpers import today_in
    from src.services import insights
    from src.services.budget import month_key

    period = month_key(today_in(db))
    snap = insights.build_digest_snapshot(db, period)

    assert "committed" in snap
    assert "committed_by_category" in snap
    assert "commitments_paid_total" in snap
    assert "other_spent" in snap
    # Portfolio is on in the test harness (conftest.py's `db` fixture) - a
    # holdings summary is built even with nothing held yet.
    assert snap["holdings_summary"] is not None
    assert snap["holdings_summary"]["top_holdings"] == []


def test_digest_snapshot_render_uses_human_labels_not_raw_keys(db):
    """A raw internal key like "stale_data" must never reach the model - it
    used to be echoed back verbatim as a headline and then mangled further
    by the Polish translator, which had no way to know it was not prose."""
    from src.routes.helpers import today_in
    from src.services import insights
    from src.services.budget import month_key

    period = month_key(today_in(db))
    snap = insights.build_digest_snapshot(db, period)
    # An empty database never has recent months recorded or fresh assets, so
    # the data_fresh rung is "todo" and its anomaly fires - see
    # services/ladder.py.
    assert any(a["key"] == "stale_data" for a in snap["anomalies"])

    text = insights.render_digest_snapshot(snap)
    assert "stale_data" not in text
    assert "data_fresh" not in text
    assert "Data up to date" in text  # the ladder line's human label
    assert "Data needs updating" in text  # the anomaly's human label


# --- /latest resumes whatever job is newest, not only a finished one -------
# (WalletAssessmentTab/ProfileTab/NextStepsTab all used to only resume a
# "done" job on mount, so a tab switch that unmounted a pending or failed
# job made it disappear until - or unless - it happened to finish.)

def test_latest_endpoint_returns_a_failed_row_not_just_done_ones(client, db):
    from src.models.insight import Insight

    db.add(Insight(kind="profile", period="", language="en", status="failed", error="boom"))
    db.commit()

    r = client.get("/api/insights/profile/latest?language=en")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "failed"
    assert r.json()["error"] == "boom"


def test_latest_endpoint_returns_the_newest_row_whatever_its_status(client, db):
    from src.models.insight import Insight

    older = Insight(kind="profile", period="", language="en", status="done", content="old")
    db.add(older)
    db.commit()
    newer = Insight(kind="profile", period="", language="en", status="pending")
    db.add(newer)
    db.commit()

    r = client.get("/api/insights/profile/latest?language=en")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == newer.id
    assert r.json()["status"] == "pending"
