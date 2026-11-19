import pytest

import queue_store


def _draft():
    return {
        "company": "Example Labs",
        "opportunity_type": "junior_vacancy",
        "vacancy_url": "https://example.test/jobs/frontend",
        "message_draft": "Draft only",
    }


def test_rejection_reason_is_saved_and_reported_without_raw_reply(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "hunter.sqlite"))
    ids = queue_store.save_outreach_drafts([_draft()])
    queue_store.update_outreach_status(ids[0], "REJECTED", feedback_reason="experience_gap")

    records = queue_store.list_outreach()
    assert records[0]["status"] == "REJECTED"
    assert records[0]["feedback_reason"] == "experience_gap"
    assert records[0]["feedback_recorded_at"]
    report = queue_store.build_outcome_feedback_report(records)
    assert "Недостаточно опыта: 1" in report
    assert "веса ATS автоматически не меняются" in report
    assert "Draft only" not in report


def test_feedback_reason_is_restricted_to_rejections_and_known_categories():
    with pytest.raises(ValueError):
        queue_store.update_outreach_status("unknown-id", "CONTACTED", feedback_reason="skills_gap")
    with pytest.raises(ValueError):
        queue_store.update_outreach_status("unknown-id", "REJECTED", feedback_reason="invented")


def test_legacy_outreach_table_gets_feedback_columns(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE outreach(
        id TEXT PRIMARY KEY, company TEXT, opportunity_type TEXT, vacancy_url TEXT,
        status TEXT, payload TEXT, created_at TEXT, updated_at TEXT,
        contacted_at TEXT, replied_at TEXT, follow_up_at TEXT)""")
    conn.commit()
    conn.close()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(db_path))

    queue_store.list_outreach()
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(outreach)")}
    conn.close()
    assert {"feedback_reason", "feedback_recorded_at"} <= columns
