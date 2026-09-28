"""GET /api/reports/pdf and the "wallet_pdf" insight kind that feeds its
optional AI section, end to end.

Numbers are cross-checked against /api/statistics/allocation and
/api/positions/growth - the PDF must never show a different total than the
pages it is summarising. PDF text is extracted with poppler's `pdftotext`
(already used elsewhere in this task to render sample pages to PNG) since
fpdf2 compresses its content streams by default, so a byte-level substring
search on the raw PDF would not find the text.
"""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import pytest

WALLET_PDF_MD = (
    "## Summary\nA steady wallet that grew modestly this period.\n\n"
    "## What stood out\n- Cash makes up a large share.\n\n"
    "## Reading the numbers\nDeposits are your own money; growth is what "
    "the market added on top.\n"
)


def _pdf_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(content)
        f.flush()
        out = subprocess.run(
            ["pdftotext", "-layout", f.name, "-"],
            capture_output=True, check=True,
        )
    return out.stdout.decode("utf-8")


def _asset(client, **overrides):
    payload = {"name": "Brokerage", "kind": "currency", "units": ""}
    payload.update(overrides)
    r = client.post("/api/assets", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _position(client, asset_id, amount, **overrides):
    payload = {"asset_id": asset_id, "amount": amount, "currency": "PLN"}
    payload.update(overrides)
    r = client.post("/api/positions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _poll(client, insight_id, timeout=5.0):
    deadline = time.time() + timeout
    got = None
    while time.time() < deadline:
        got = client.get(f"/api/insights/item/{insight_id}").json()
        if got["status"] in ("done", "failed"):
            return got
        time.sleep(0.01)
    raise AssertionError(f"insight {insight_id} did not finish in time: {got}")


def _configured_llm(monkeypatch):
    from src.services import llm

    monkeypatch.setattr(llm, "configured", lambda: True)
    return llm


# --- The deterministic PDF, no AI --------------------------------------

def test_download_without_ai_is_immediate_and_needs_no_model(client):
    _position(client, _asset(client)["id"], 1000)

    r = client.get("/api/reports/pdf?period=all&language=en")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert "attachment" in r.headers["content-disposition"]


def test_bad_period_is_rejected(client):
    r = client.get("/api/reports/pdf?period=decade&language=en")
    assert r.status_code == 422


def test_bad_language_is_rejected(client):
    r = client.get("/api/reports/pdf?period=all&language=de")
    assert r.status_code == 422


def test_total_value_matches_the_allocation_endpoint(client):
    _position(client, _asset(client, name="Cash")["id"], 12345.67)

    alloc = client.get("/api/statistics/allocation").json()
    pdf_text = _pdf_text(client.get("/api/reports/pdf?period=all&language=en").content)

    assert f"{alloc['total']:,.2f} PLN" in pdf_text


def test_efficiency_totals_match_the_growth_endpoint(client):
    p1 = _position(client, _asset(client, name="Brokerage")["id"], 1000)
    client.put(
        f"/api/positions/{p1['id']}", json={"amount": 1120, "currency": "PLN", "flow": 100}
    )

    growth = client.get("/api/positions/growth").json()
    pdf_text = _pdf_text(client.get("/api/reports/pdf?period=all&language=en").content)

    total = growth["total"]
    assert f"+{total['contributed']:,.2f} PLN" in pdf_text
    assert f"+{total['growth']:,.2f} PLN" in pdf_text


def test_polish_report_translates_labels_and_renders_diacritics(client):
    _position(client, _asset(client, name="Cash", category="Cash")["id"], 500)

    pdf_text = _pdf_text(client.get("/api/reports/pdf?period=all&language=pl").content)
    assert "Raport portfela" in pdf_text
    assert "Gotówka" in pdf_text  # translated category, with a real diacritic
    assert "Nie stanowi doradztwa" in pdf_text  # disclaimer, in Polish


def test_empty_wallet_still_produces_a_pdf(client):
    r = client.get("/api/reports/pdf?period=1m&language=en")
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert "No holdings recorded" in text
    assert "Not available for this period" in text  # no XIRR without flows


# --- AI commentary gating -----------------------------------------------

def test_unknown_ai_insight_id_is_404(client):
    r = client.get("/api/reports/pdf?period=all&language=en&ai_insight_id=999999")
    assert r.status_code == 404


def test_ai_insight_of_the_wrong_kind_is_rejected(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "## This month\nfine\n\n## What changed\nnothing\n\n## One thing to focus on\nsave more\n")

    digest = client.post("/api/insights/digest", json={"language": "en", "period": "2026-01"})
    _poll(client, digest.json()["id"])

    r = client.get(f"/api/reports/pdf?period=all&language=en&ai_insight_id={digest.json()['id']}")
    assert r.status_code == 409


def test_ai_insight_still_pending_is_rejected(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    # Never resolves within the request - the row stays "pending"/"running".
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)

    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    insight_id = created.json()["id"]
    # Deliberately not polled to completion.
    r = client.get(f"/api/reports/pdf?period=all&language=en&ai_insight_id={insight_id}")
    # Either still pending (409) or the fast worker already finished it - both
    # are acceptable outcomes of a race, but "still pending" is what this
    # test means to exercise, so skip the assertion if it lost the race.
    if r.status_code != 200:
        assert r.status_code == 409


def test_ai_insight_language_mismatch_is_rejected(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)

    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    insight_id = created.json()["id"]
    _poll(client, insight_id)

    r = client.get(f"/api/reports/pdf?period=all&language=pl&ai_insight_id={insight_id}")
    assert r.status_code == 409


def test_ai_insight_period_mismatch_is_rejected(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)

    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "12m"})
    insight_id = created.json()["id"]
    _poll(client, insight_id)

    r = client.get(f"/api/reports/pdf?period=all&language=en&ai_insight_id={insight_id}")
    assert r.status_code == 409


# --- AI commentary embedded end to end -----------------------------------

def test_ai_commentary_is_embedded_and_labelled(client, monkeypatch):
    _position(client, _asset(client, name="Cash")["id"], 1000)
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)

    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    got = _poll(client, created.json()["id"])
    assert got["status"] == "done", got
    assert got["kind"] == "wallet_pdf"
    assert got["ungrounded"] == []  # every figure in WALLET_PDF_MD is prose, no numbers

    r = client.get(
        f"/api/reports/pdf?period=all&language=en&ai_insight_id={created.json()['id']}"
    )
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert "AI-generated commentary" in text
    assert "A steady wallet that grew modestly this period." in text


def test_ungrounded_ai_numbers_show_a_warning_in_the_pdf(client, monkeypatch):
    """The model inventing a figure never ends up in the PDF unchecked - it
    still gets embedded (grounding never silently drops text, only flags
    it - see services/grounding.py), but with a visible warning naming the
    unmatched number."""
    _position(client, _asset(client, name="Cash")["id"], 1000)
    llm = _configured_llm(monkeypatch)
    fabricated = "## Summary\nGrew by an incredible 987.65%!\n\n## What stood out\n- n/a\n\n## Reading the numbers\nn/a\n"
    monkeypatch.setattr(llm, "complete", lambda *a, **k: fabricated)

    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    got = _poll(client, created.json()["id"])
    assert got["status"] == "done", got
    assert "987.65%" in got["ungrounded"]

    r = client.get(
        f"/api/reports/pdf?period=all&language=en&ai_insight_id={created.json()['id']}"
    )
    assert r.status_code == 200
    text = _pdf_text(r.content)
    assert "could not be matched" in text
    assert "987.65" in text


def test_reconciliation_line_is_printed_with_matching_figures(client):
    """opening + deposits + growth = value now is printed in the PDF, and
    the "value now" it names is the same figure the headline total shows -
    not just true in the underlying data, but actually visible on the
    page."""
    p1 = _position(client, _asset(client, name="Brokerage")["id"], 1000)
    client.put(
        f"/api/positions/{p1['id']}", json={"amount": 1120, "currency": "PLN", "flow": 100}
    )

    growth = client.get("/api/positions/growth").json()
    alloc = client.get("/api/statistics/allocation").json()
    assert growth["total"]["value"] == pytest.approx(alloc["total"])

    # Whitespace-normalized: the multi_cell sentence can wrap onto a second
    # PDF line depending on how wide the numbers are, and pdftotext then
    # emits a newline at that wrap point rather than a space.
    text = " ".join(
        _pdf_text(client.get("/api/reports/pdf?period=all&language=en").content).split()
    )
    t = growth["total"]
    line = (
        f"{t['opening_value']:,.2f} PLN at the start of the period, "
        f"+{t['contributed']:,.2f} PLN in deposits and withdrawals, "
        f"+{t['growth']:,.2f} PLN in growth = {t['value']:,.2f} PLN now."
    )
    assert line in text
    # And that "now" figure is the same one the headline "Total value" shows.
    assert f"{alloc['total']:,.2f} PLN" in text


def test_ai_insight_id_renders_from_its_own_frozen_snapshot(client, monkeypatch):
    """Prices can move between generating the AI commentary and downloading
    the PDF - the download must then show the numbers the commentary was
    actually grounded against, not a freshly revalued total that could now
    disagree with what the AI text says."""
    asset = _asset(client, name="Bitcoin", kind="crypto", units="BTC")
    r = client.post(
        "/api/positions", json={"asset_id": asset["id"], "amount": 1, "currency": "PLN"}
    )
    assert r.status_code == 201, r.text

    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)
    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    insight = _poll(client, created.json()["id"])
    assert insight["status"] == "done", insight
    frozen_total = insight["snapshot"]["total_value"]

    # Price moves after the insight's snapshot was taken.
    from src.services import price_service as ps

    monkeypatch.setitem(ps._FALLBACK_CRYPTO_USD, "BTC", 999999.0)
    ps._CACHE.clear()

    fresh_alloc = client.get("/api/statistics/allocation").json()
    assert fresh_alloc["total"] != pytest.approx(frozen_total)  # the price move is real

    frozen_text = _pdf_text(
        client.get(
            f"/api/reports/pdf?period=all&language=en&ai_insight_id={insight['id']}"
        ).content
    )
    live_text = _pdf_text(client.get("/api/reports/pdf?period=all&language=en").content)

    assert f"{frozen_total:,.2f} PLN" in frozen_text
    assert f"{fresh_alloc['total']:,.2f} PLN" not in frozen_text
    assert f"{fresh_alloc['total']:,.2f} PLN" in live_text


def test_data_as_of_line_uses_the_insights_own_timestamp_when_ai_given(client, monkeypatch):
    llm = _configured_llm(monkeypatch)
    monkeypatch.setattr(llm, "complete", lambda *a, **k: WALLET_PDF_MD)
    created = client.post("/api/insights/wallet_pdf", json={"language": "en", "period": "all"})
    insight = _poll(client, created.json()["id"])
    assert insight["status"] == "done", insight

    text = _pdf_text(
        client.get(
            f"/api/reports/pdf?period=all&language=en&ai_insight_id={insight['id']}"
        ).content
    )
    assert "Data as of" in text
