"""Statement import assistant: the Settings switch and the three server jobs.

The model is faked: these tests pin the gating (only "server" mode, only with
a model configured), the request limits, and that every answer is checked
against what was offered before it is returned.
"""
import json

import pytest


@pytest.fixture
def fake_llm(monkeypatch):
    """llm.configured() true, llm.complete() answering with whatever the test
    queues; records each call so a test can look at what was sent."""
    from src.services import llm

    answers: list = []
    calls: list[dict] = []

    def complete(model, system, user, **kw):
        calls.append({"model": model, "system": system, "user": user, **kw})
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a)

    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "complete", complete)
    return answers, calls, llm


def _server_mode(client):
    r = client.put("/api/settings/statement-assist", json={"mode": "server"})
    assert r.status_code == 200, r.text
    return r.json()


def test_default_is_off_and_server_needs_a_model(client):
    s = client.get("/api/settings").json()
    assert s["statement_assist"] == "off"
    assert s["statement_assist_server"] is False
    assert client.put("/api/settings/statement-assist", json={"mode": "server"}).status_code == 422
    r = client.put("/api/settings/statement-assist", json={"mode": "browser"})
    assert r.status_code == 200 and r.json()["statement_assist"] == "browser"
    assert client.put("/api/settings/statement-assist", json={"mode": "cloud"}).status_code == 422


def test_jobs_refused_unless_server_mode(client, fake_llm):
    body = {"lines": ["01.10.2026  Sklep  45,99"], "first_line": 1}
    assert client.post("/api/statement/extract", json=body).status_code == 409
    client.put("/api/settings/statement-assist", json={"mode": "browser"})
    assert client.post("/api/statement/extract", json=body).status_code == 409


def test_columns_clamps_indices(client, fake_llm):
    answers, calls, _ = fake_llm
    assert _server_mode(client)["statement_assist"] == "server"
    answers.append({"date": 0, "amount": 9, "debit": 2, "credit": -1, "outgoing": "positive",
                    "description": [1, 7], "currency": -1})
    r = client.post("/api/statement/columns", json={
        "header": ["Data", "Opis", "Obciążenia", "Uznania"],
        "sample": [["01.10.2026", "Sklep", "45,99", ""]],
    })
    assert r.status_code == 200, r.text
    assert r.json() == {"date": 0, "amount": -1, "debit": 2, "credit": -1, "outgoing": "positive",
                        "description": [1], "currency": -1}
    assert calls[0]["model"] == "Bielik"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["timeout"] < 60


def test_extract_keeps_lines_of_this_chunk_only(client, fake_llm):
    answers, calls, _ = fake_llm
    _server_mode(client)
    answers.append("Here you go:\n" + json.dumps({"transactions": [
        {"line": 11, "date": "2026-10-01", "amount": -45.99, "direction": "out", "currency": "PLN",
         "description": "Sklep"},
        {"line": 99, "date": "2026-10-02", "amount": 10, "direction": "out", "currency": "PLN",
         "description": "elsewhere"},
    ]}))
    r = client.post("/api/statement/extract", json={"lines": ["a", "01.10.2026 Sklep 45,99"], "first_line": 10})
    assert r.status_code == 200, r.text
    assert r.json()["transactions"] == [
        {"line": 11, "date": "2026-10-01", "amount": 45.99, "direction": "out", "currency": "PLN",
         "description": "Sklep"}
    ]
    assert "L10: a\nL11: 01.10.2026" in calls[0]["user"]


def test_match_only_offered_ids_each_payment_once(client, fake_llm):
    answers, _, _ = fake_llm
    _server_mode(client)
    answers.append({"matches": [
        {"commitment": 1, "payment": 10},
        {"commitment": 2, "payment": 10},  # payment already used
        {"commitment": 3, "payment": 11},  # commitment never offered
        {"commitment": 2, "payment": 12},
    ]})
    r = client.post("/api/statement/match", json={
        "commitments": [
            {"id": 1, "name": "Prąd", "category": "Mieszkanie", "amount": 180, "currency": "PLN"},
            {"id": 2, "name": "Internet", "amount": 60},
        ],
        "payments": [
            {"id": 10, "date": "2026-10-05", "amount": 172.4, "note": "PGE OBRÓT"},
            {"id": 11, "date": "2026-10-06", "amount": 99, "note": "Sklep"},
            {"id": 12, "date": "2026-10-07", "amount": 59.99, "note": "UPC"},
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["matches"] == [{"commitment": 1, "payment": 10}, {"commitment": 2, "payment": 12}]


def test_model_without_schema_support_is_asked_again_plainly(client, fake_llm):
    answers, calls, llm = fake_llm
    _server_mode(client)
    answers.append(llm.LLMBadRequest("Model server returned 400: Failed to initialize samplers"))
    answers.append('{"1": 10, "2": -1}')
    r = client.post("/api/statement/match", json={
        "commitments": [{"id": 1, "name": "Prąd", "amount": 180}, {"id": 2, "name": "Internet", "amount": 60}],
        "payments": [{"id": 10, "date": "2026-10-05", "amount": 172.4, "note": "PGE OBRÓT"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["matches"] == [{"commitment": 1, "payment": 10}]
    assert calls[0]["response_format"] is not None and calls[1]["response_format"] is None


def test_model_failure_is_503_without_the_statement_text(client, fake_llm):
    answers, _, llm = fake_llm
    _server_mode(client)
    answers.append(llm.LLMUnavailable("timeout while sending L1: 01.10.2026 SECRET SHOP 45,99"))
    r = client.post("/api/statement/extract", json={"lines": ["01.10.2026 SECRET SHOP 45,99"]})
    assert r.status_code == 503
    assert "SECRET" not in r.text
    answers.append("no json at all")
    assert client.post("/api/statement/extract", json={"lines": ["x"]}).status_code == 502


def test_request_limits(client, fake_llm):
    _server_mode(client)
    assert client.post("/api/statement/extract", json={"lines": ["x"] * 41}).status_code == 422
    assert client.post("/api/statement/extract", json={"lines": ["x" * 301]}).status_code == 422
    assert client.post("/api/statement/columns", json={"header": ["a"], "sample": [["b"]] * 9}).status_code == 422
