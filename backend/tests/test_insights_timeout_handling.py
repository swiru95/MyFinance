"""Timeout and unavailability handling in insight jobs.

When the translator becomes unavailable during localize_data (per-leaf
fallback) or during the main content translation, the job should degrade
gracefully without multiplying timeouts.
"""
import json
import time

PROFILE_JSON = {
    "stated_tolerance": "medium",
    "capacity": "high",
    "revealed": "low",
    "mismatches": [],
    "priorities": ["Build an emergency fund"],
    "suggested_style": "balanced",
    "summary_md": "This wallet mixes stable income with a cautious allocation.",
}

DIGEST_MD = (
    "## This month\nNothing much happened.\n\n"
    "## What changed\nNo prior data to compare.\n\n"
    "## One thing to focus on\nStart tracking your spending.\n"
)


def _configured_llm(monkeypatch):
    from src.services import llm

    monkeypatch.setattr(llm, "configured", lambda: True)
    return llm


def _poll(client, insight_id, timeout=5.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = client.get(f"/api/insights/item/{insight_id}").json()
        if got["status"] in ("done", "failed"):
            return got
        time.sleep(0.01)
    raise AssertionError(f"insight {insight_id} did not finish in time: {got}")


def test_bulk_translation_timeout_makes_no_perleaf_calls(client, monkeypatch):
    """When bulk array translation times out (LLMUnavailable), don't retry
    with per-leaf calls - return immediately. This test focuses on the
    data localization part of a Polish profile."""
    llm = _configured_llm(monkeypatch)
    call_count = {"bulk": 0, "leaf": 0, "content_trans": 0, "profile_gen": 0}

    def fake_complete(model, system, user, *, temperature=0.2, max_tokens=None, response_format=None):
        # Count calls to distinguish types
        if "localized_strings" in str(response_format or ""):
            # Data localization bulk call
            call_count["bulk"] += 1
            raise llm.LLMUnavailable("data server unreachable")
        elif max_tokens == 512:  # llm_translate_max_tokens for per-leaf
            # Per-leaf call (should not happen)
            call_count["leaf"] += 1
            return user
        elif model == "Bielik":
            # Content translation to Polish
            call_count["content_trans"] += 1
            return "Polish content"
        else:
            # Profile generation (Thinker)
            call_count["profile_gen"] += 1
            return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    assert r.status_code == 202, r.text
    got = _poll(client, r.json()["id"])

    # Job should complete (data translation is secondary)
    assert got["status"] == "done", got
    # Content should be the Polish translation (not data localization timeout)
    assert got["content"] == "Polish content", got
    # Data localization bulk timeout happened, no per-leaf fallback
    assert call_count["bulk"] >= 1, "Should attempt bulk data localization"
    assert call_count["leaf"] == 0, f"Should not retry per-leaf after bulk timeout, but got {call_count['leaf']} calls"


def test_content_translation_timeout_skips_data_localization(client, monkeypatch):
    """When translate_to_polish times out with LLMUnavailable (not
    LLMBadRequest), skip localize_data entirely rather than trying per-leaf
    calls on the data."""
    llm = _configured_llm(monkeypatch)
    call_count = {"content": 0, "data_bulk": 0, "data_leaf": 0}

    def fake_complete(model, system, user, *, temperature=0.2, max_tokens=None, response_format=None):
        # Count calls by checking the system prompt or other distinguishing features
        if "localized_strings" in str(response_format or ""):
            # Data localization bulk call
            call_count["data_bulk"] += 1
            return json.dumps(["translated"])
        elif max_tokens == 512:  # llm_translate_max_tokens for per-leaf
            # Data localization per-leaf
            call_count["data_leaf"] += 1
            return user
        elif model == "Bielik":
            # Content translation to Polish (Bielik model)
            call_count["content"] += 1
            raise llm.LLMUnavailable("translator timed out")
        # Profile generation (Thinker model)
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    # Job should complete with content translation failure note
    assert got["status"] == "done", got
    assert "Could not translate" in got["error"], f"Expected error note, got: {got['error']}"
    # Content translation was attempted and timed out
    assert call_count["content"] >= 1, "Should attempt content translation"
    # But data localization should not have been attempted
    # since the translator is down (LLMUnavailable, not LLMBadRequest)
    assert call_count["data_bulk"] == 0, f"Should skip data localization when translator times out, but got {call_count['data_bulk']} bulk calls"
    assert call_count["data_leaf"] == 0, f"Should skip data localization when translator times out, but got {call_count['data_leaf']} leaf calls"


def test_per_leaf_stops_at_first_timeout(client, monkeypatch):
    """When a per-leaf translation times out, stop immediately and keep
    English for remaining leaves instead of trying each leaf."""
    llm = _configured_llm(monkeypatch)
    leaf_calls: list[str] = []

    def fake_complete(model, system, user, *, temperature=0.2, max_tokens=None, response_format=None):
        # Data localization
        if "localized_strings" in str(response_format or ""):
            # Bulk call returns wrong shape, trigger per-leaf fallback
            raise llm.LLMUnavailable("bulk timeout")
        elif max_tokens == 512:  # llm_translate_max_tokens for per-leaf
            leaf_calls.append(user)
            if len(leaf_calls) >= 2:
                # Second leaf times out
                raise llm.LLMUnavailable("per-leaf timeout")
            return f"translated: {user}"
        # Profile generation
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    # Job completes with data translation note
    assert got["status"] == "done", got
    # Should have attempted only 1 leaf before timing out on the 2nd
    assert len(leaf_calls) <= 2, f"Should stop at first timeout, but got {len(leaf_calls)} leaf calls"
    # The note should mention that translation is unavailable
    assert "Data translation unavailable" in got.get("error", ""), got


def test_localize_data_distinguishes_timeout_from_shape_error(client, monkeypatch):
    """Timeout (LLMUnavailable) is treated differently from malformed
    response (ValueError) - timeout returns None immediately, shape error
    tries per-leaf fallback."""
    llm = _configured_llm(monkeypatch)
    calls: list[str] = []

    def fake_complete(model, system, user, *, temperature=0.2, max_tokens=None, response_format=None):
        if "localized_strings" in str(response_format or ""):
            # Bulk call
            calls.append("bulk")
            raise llm.LLMUnavailable("timeout")
        elif max_tokens == 512:
            # Per-leaf call (should not happen)
            calls.append("leaf")
            return user
        # Profile generation
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    assert got["status"] == "done", got
    # Only the bulk call should have been made (no per-leaf retry on timeout)
    assert calls == ["bulk"], f"Expected only bulk call on timeout, but got {calls}"


def test_content_translation_bad_request_still_tries_data_localization(client, monkeypatch):
    """When translate_to_polish raises LLMBadRequest (client error, not
    unavailability), localize_data should still be attempted."""
    llm = _configured_llm(monkeypatch)
    call_count = {"content": 0, "data": 0}

    def fake_complete(model, system, user, *, temperature=0.2, max_tokens=None, response_format=None):
        if "localized_strings" in str(response_format or ""):
            # Data localization
            call_count["data"] += 1
            return json.dumps(["translated"])
        elif model == "Bielik" and max_tokens == 2048:
            # Content translation fails with bad request
            call_count["content"] += 1
            raise llm.LLMBadRequest("unsupported model version")
        # Profile generation
        return json.dumps(PROFILE_JSON)

    monkeypatch.setattr(llm, "complete", fake_complete)

    r = client.post("/api/insights/profile", json={"language": "pl"})
    got = _poll(client, r.json()["id"])

    # Job should complete with content translation note
    assert got["status"] == "done", got
    # Data localization should have been attempted (client error != unavailable)
    assert call_count["data"] >= 1, "Should attempt data localization after LLMBadRequest"


def test_perleaf_timeout_counts_remaining_as_failures():
    """When per-leaf translation times out at the first leaf, remaining
    leaves should be counted as failures (via failures += len(leaves) - i)
    so localize_data knows to report 'Data translation unavailable'."""
    import unittest.mock as mock
    from src.services import insights as insights_service
    from src.services import llm

    leaves = ["leaf1", "leaf2", "leaf3"]
    call_count = [0]

    def mock_translate_leaf(model, leaf):
        call_count[0] += 1
        if call_count[0] == 1:
            # First leaf times out
            raise llm.LLMUnavailable("timeout")
        # Shouldn't reach here
        return f"translated_{leaf}"

    # Mock the _translate_leaf function directly
    with mock.patch.object(insights_service, "_translate_leaf", side_effect=mock_translate_leaf):
        translated, failures = insights_service._translate_leaves_individually("Bielik", leaves)

    # First leaf times out, so all 3 should be counted as failures
    assert translated == leaves, "All leaves should remain English"
    assert failures == 3, f"All 3 leaves should count as failures (0+3), got {failures}"
    assert call_count[0] == 1, f"Should only attempt first leaf before timeout, got {call_count[0]} attempts"
