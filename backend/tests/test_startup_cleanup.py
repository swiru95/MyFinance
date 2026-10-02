"""Startup cleanup of interrupted LLM jobs.

When the application starts, any pending/running/translating Report or Insight
rows left from a crash/restart of the previous instance are swept:
- Translating rows -> marked done with a note (a job only enters 'translating'
  after its English text is stored, so there is always something to show)
- All other pending/running/translating -> marked failed with a note

The sweep holds no key, so it cannot read or write anything encrypted: it changes
`status` and a plaintext `status_note` code, and the model turns that code back
into the text a user reads (models/jobnotes.py). The tests below also check that.
"""
import pytest

from src.models.report import Report
from src.models.insight import Insight
from src.services.llm_queue import cleanup_interrupted_jobs


def test_cleanup_reports_pending_to_failed(db):
    """A Report left in 'pending' state is marked 'failed' on cleanup."""
    report = Report(
        style="balanced",
        language="en",
        status="pending",
    )
    db.add(report)
    db.commit()
    report_id = report.id

    cleanup_interrupted_jobs()

    db.refresh(report)
    assert report.status == "failed"
    assert report.error == "Interrupted by a server restart - generate again."


def test_cleanup_reports_running_to_failed(db):
    """A Report left in 'running' state is marked 'failed' on cleanup."""
    report = Report(
        style="safe",
        language="en",
        status="running",
    )
    db.add(report)
    db.commit()

    cleanup_interrupted_jobs()

    db.refresh(report)
    assert report.status == "failed"
    assert report.error == "Interrupted by a server restart - generate again."


def test_cleanup_reports_translating_with_content_to_done(db):
    """A Report in 'translating' with content set is marked 'done' with note."""
    english_md = "## Summary\nA portfolio.\n"
    report = Report(
        style="balanced",
        language="pl",
        status="translating",
        content=english_md,
        content_en=english_md,
    )
    db.add(report)
    db.commit()

    cleanup_interrupted_jobs()

    db.refresh(report)
    assert report.status == "done"
    assert "Translation was interrupted by a server restart" in report.error
    assert report.content == english_md


def test_cleanup_never_needs_to_read_the_content(db):
    """The sweep is status-only: it works on a session that holds no key, which
    is the point - the system session could not decrypt `content` if it tried."""
    from src.crypto.core import KeysUnavailable
    from tests.conftest import system_session

    report = Report(style="balanced", language="pl", status="translating", content="secret text")
    db.add(report)
    db.commit()

    cleanup_interrupted_jobs()

    sysdb = system_session()
    try:
        with pytest.raises(KeysUnavailable):
            sysdb.query(Report).all()  # sanity: reading the row without a key is refused
        assert sysdb.query(Report.status, Report.status_note).all() == [("done", "translation_interrupted")]
    finally:
        sysdb.close()


def test_cleanup_insights_pending_to_failed(db):
    """An Insight left in 'pending' state is marked 'failed' on cleanup."""
    insight = Insight(
        kind="profile",
        status="pending",
        language="en",
    )
    db.add(insight)
    db.commit()

    cleanup_interrupted_jobs()

    db.refresh(insight)
    assert insight.status == "failed"
    assert insight.error == "Interrupted by a server restart - generate again."


def test_cleanup_insights_running_to_failed(db):
    """An Insight left in 'running' state is marked 'failed' on cleanup."""
    insight = Insight(
        kind="digest",
        period="2026-09",
        status="running",
        language="en",
    )
    db.add(insight)
    db.commit()

    cleanup_interrupted_jobs()

    db.refresh(insight)
    assert insight.status == "failed"
    assert insight.error == "Interrupted by a server restart - generate again."


def test_cleanup_insights_translating_with_content_to_done(db):
    """An Insight in 'translating' with content set is marked 'done' with note."""
    english_md = "## This month\nNothing happened.\n"
    insight = Insight(
        kind="next_steps",
        status="translating",
        language="pl",
        content=english_md,
        content_en=english_md,
    )
    db.add(insight)
    db.commit()

    cleanup_interrupted_jobs()

    db.refresh(insight)
    assert insight.status == "done"
    assert "Translation was interrupted by a server restart" in insight.error
    assert insight.content == english_md


def test_cleanup_mixed_orphaned_jobs(db):
    """Multiple orphaned reports and insights in various states are all fixed."""
    # Create orphaned reports
    report1 = Report(style="balanced", language="en", status="pending")
    report2 = Report(style="safe", language="en", status="running")
    report3 = Report(
        style="risky",
        language="pl",
        status="translating",
        content="English report content",
        content_en="English report content",
    )

    # Create orphaned insights
    insight1 = Insight(kind="profile", status="pending", language="en")
    insight2 = Insight(kind="digest", period="2026-09", status="running", language="en")
    insight3 = Insight(
        kind="next_steps",
        status="translating",
        language="pl",
        content="English insight content",
        content_en="English insight content",
    )

    db.add_all([report1, report2, report3, insight1, insight2, insight3])
    db.commit()

    cleanup_interrupted_jobs()

    # Refresh and check all rows
    db.refresh(report1)
    db.refresh(report2)
    db.refresh(report3)
    db.refresh(insight1)
    db.refresh(insight2)
    db.refresh(insight3)

    # Pending/running reports -> failed
    assert report1.status == "failed"
    assert report1.error == "Interrupted by a server restart - generate again."

    assert report2.status == "failed"
    assert report2.error == "Interrupted by a server restart - generate again."

    # Translating with content -> done
    assert report3.status == "done"
    assert "Translation was interrupted" in report3.error

    # Pending/running insights -> failed
    assert insight1.status == "failed"
    assert insight1.error == "Interrupted by a server restart - generate again."

    assert insight2.status == "failed"
    assert insight2.error == "Interrupted by a server restart - generate again."

    # Translating with content -> done
    assert insight3.status == "done"
    assert "Translation was interrupted" in insight3.error


def test_cleanup_leaves_done_rows_alone(db):
    """Rows already marked 'done' or 'failed' are not touched."""
    report_done = Report(
        style="balanced",
        language="en",
        status="done",
        content="Already done",
    )
    report_failed = Report(
        style="safe",
        language="en",
        status="failed",
        error="Already failed",
    )

    db.add_all([report_done, report_failed])
    db.commit()

    original_done_content = report_done.content
    original_failed_error = report_failed.error

    cleanup_interrupted_jobs()

    db.refresh(report_done)
    db.refresh(report_failed)

    assert report_done.status == "done"
    assert report_done.content == original_done_content

    assert report_failed.status == "failed"
    assert report_failed.error == original_failed_error


def test_cleanup_handles_empty_tables(db):
    """Cleanup succeeds gracefully when tables have no orphaned rows."""
    # Just call cleanup on empty/clean database
    cleanup_interrupted_jobs()
    # Should not raise
