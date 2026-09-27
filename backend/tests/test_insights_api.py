"""Insight jobs end to end: POST -> worker thread -> poll to done, with
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
            raise llm.LLMUnavailable("this server does not support response_format")
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "en"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert len(calls) == 2
    assert calls[0] is not None
    assert calls[1] is None


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
    llm = _configured_llm(monkeypatch)
    translated_data = {
        "summary_md": "To portfolio laczy stabilny dochod z ostroznym rozlokowaniem.",
        "priorities": ["Zbuduj fundusz awaryjny"],
        "mismatches": [],
    }

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            assert response_format is not None
            return json.dumps(PROFILE_JSON)
        if model == "Bielik":
            if response_format is None:
                # The Markdown content_en -> content translation pass.
                return "## Podsumowanie\nPrzetlumaczony tekst raportu."
            # The structured data -> data_localized translation pass.
            payload = json.loads(user)
            assert set(payload.keys()) == {"summary_md", "priorities", "mismatches"}
            return json.dumps(translated_data)
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is not None
    assert got["data_localized"]["summary_md"] == translated_data["summary_md"]
    assert got["data_localized"]["priorities"] == translated_data["priorities"]
    # Enums and keys are copied through untouched, not re-translated.
    assert got["data_localized"]["stated_tolerance"] == got["data"]["stated_tolerance"]
    assert got["data_localized"]["capacity"] == got["data"]["capacity"]
    assert got["data_localized"]["revealed"] == got["data"]["revealed"]
    assert got["data_localized"]["suggested_style"] == got["data"]["suggested_style"]
    # The English data is untouched by the translation.
    assert got["data"]["summary_md"] == PROFILE_JSON["summary_md"]


def test_profile_pl_wrong_translation_shape_leaves_data_localized_none(client, monkeypatch):
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            return json.dumps(PROFILE_JSON)
        if model == "Bielik":
            if response_format is None:
                return "## Podsumowanie\nPrzetlumaczony tekst raportu."
            # Missing keys / wrong shape - not what localize_data asked for.
            return json.dumps({"unexpected": "shape"})
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
    translated_data = {
        "steps": [
            {
                "title": "Ustaw cel FIRE",
                "why_md": "Planowanie wymaga roku urodzenia i docelowego wieku.",
            },
        ],
    }

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Thinker":
            assert response_format is not None
            return json.dumps(steps_json)
        if model == "Bielik":
            if response_format is None:
                return "## Kolejny krok\nUstaw cel FIRE."
            payload = json.loads(user)
            assert payload == {
                "steps": [
                    {
                        "title": "Set your FIRE target",
                        "why_md": "Planning needs a birth year and a target age to work from.",
                    },
                ],
            }
            return json.dumps(translated_data)
        raise AssertionError(model)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/next_steps", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["data_localized"] is not None
    loc_step = got["data_localized"]["steps"][0]
    assert loc_step["title"] == "Ustaw cel FIRE"
    assert loc_step["why_md"] == "Planowanie wymaga roku urodzenia i docelowego wieku."
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
