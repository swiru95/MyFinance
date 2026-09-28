"""Wallet assessment jobs end to end: POST -> shared LLM queue -> poll to
done, with services.llm.complete monkeypatched so no test ever reaches a
real model. Mirrors tests/test_insights_api.py's shape.
"""
import time

REPORT_MD = (
    "## Summary\nA steady, cautious portfolio.\n\n"
    "## What stands out\n- Mostly cash, PLN 10,000.00, 100.0%\n\n"
    "## Risks\n- No diversification.\n\n"
    "## Recommendations\n1. Add some equity exposure.\n"
)


def _poll(client, report_id, timeout=5.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = client.get(f"/api/reports/{report_id}").json()
        if got["status"] in ("done", "failed"):
            return got
        time.sleep(0.01)
    raise AssertionError(f"report {report_id} did not finish in time: {got}")


def _configured_llm(monkeypatch):
    from src.services import llm

    monkeypatch.setattr(llm, "configured", lambda: True)
    return llm


def test_status_reports_unconfigured_by_default(client):
    body = client.get("/api/reports/status").json()
    assert body["configured"] is False
    assert body["model"] == "Thinker"


def test_post_returns_503_when_not_configured(client):
    r = client.post("/api/reports", json={"style": "balanced", "language": "en"})
    assert r.status_code == 503, r.text


def test_report_job_completes_in_english(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: REPORT_MD)

    r = client.post("/api/reports", json={"style": "balanced", "language": "en"})
    assert r.status_code == 202, r.text
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert "## Summary" in got["content"]
    assert got["model"] == "Thinker"
    assert got["translator"] == ""
    assert got["error"] == ""


def test_report_job_translates_to_polish(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    polish_md = "## Podsumowanie\nStabilny, ostrozny portfel."

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        return polish_md if model == "Bielik" else REPORT_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/reports", json={"style": "safe", "language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert got["translator"] == "Bielik"
    assert "Podsumowanie" in got["content"]
    assert got["error"] == ""


def test_failed_polish_translation_ends_done_with_english_and_a_note(client, monkeypatch):
    """A translation hiccup must not throw away an already-finished English
    report - the job still ends "done", with the English text and a note on
    `error`, not "failed"."""
    llm = _configured_llm(monkeypatch)

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        if model == "Bielik":
            raise llm.LLMUnavailable("model server unreachable")
        return REPORT_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/reports", json={"style": "balanced", "language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    assert "## Summary" in got["content"]  # the English report, not lost
    assert got["translator"] == ""
    assert "Could not translate to Polish" in got["error"]


def test_report_history_list_and_delete(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: REPORT_MD)

    r = client.post("/api/reports", json={"style": "balanced", "language": "en"})
    report_id = r.json()["id"]
    _poll(client, report_id)

    listing = client.get("/api/reports").json()
    assert any(row["id"] == report_id for row in listing)

    delete = client.delete(f"/api/reports/{report_id}")
    assert delete.status_code == 204
    assert client.get(f"/api/reports/{report_id}").status_code == 404


def test_report_and_insight_jobs_never_generate_concurrently(client, monkeypatch):
    """Reports and insights now share one process-wide LLM queue
    (services/llm_queue.py) precisely because the model server holds one
    model resident at a time - two jobs queued close together must run one
    after another, never overlapping."""
    llm = _configured_llm(monkeypatch)
    import json
    import threading

    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        if response_format is not None:
            return json.dumps({
                "stated_tolerance": "medium", "capacity": "high", "revealed": "low",
                "mismatches": [], "priorities": [], "suggested_style": "balanced",
                "summary_md": "Fine.",
            })
        return REPORT_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r1 = client.post("/api/reports", json={"style": "balanced", "language": "en"})
    r2 = client.post("/api/insights/profile", json={"language": "en"})
    report_id, insight_id = r1.json()["id"], r2.json()["id"]

    _poll(client, report_id)
    deadline = time.time() + 5.0
    insight_status = None
    while time.time() < deadline:
        insight_status = client.get(f"/api/insights/item/{insight_id}").json()
        if insight_status["status"] in ("done", "failed"):
            break
        time.sleep(0.01)
    assert insight_status is not None and insight_status["status"] == "done", insight_status

    assert max_in_flight == 1


def test_queued_job_stays_pending_while_another_runs(client, monkeypatch):
    """A job queued behind another one stays "pending" (never "running")
    until the shared worker actually picks it up - see services/
    llm_queue.py."""
    llm = _configured_llm(monkeypatch)
    import threading

    started = threading.Event()
    release = threading.Event()

    def fake_complete(model, system, user, *, temperature=0.3, max_tokens=4096, response_format=None):
        started.set()
        release.wait(timeout=5)
        return REPORT_MD

    monkeypatch.setattr(llm, "complete", fake_complete)

    r1 = client.post("/api/reports", json={"style": "balanced", "language": "en"})
    id1 = r1.json()["id"]
    assert started.wait(timeout=2), "first job never started"

    r2 = client.post("/api/reports", json={"style": "safe", "language": "en"})
    id2 = r2.json()["id"]

    time.sleep(0.1)
    row2 = client.get(f"/api/reports/{id2}").json()
    assert row2["status"] == "pending", row2

    release.set()
    _poll(client, id1)
    _poll(client, id2)
