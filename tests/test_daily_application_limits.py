from datetime import datetime
from zoneinfo import ZoneInfo

import queue_store


def _use_temp_db(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "queue.sqlite3"))
    local = datetime(2026, 11, 11, 12, 0, tzinfo=ZoneInfo("Europe/Amsterdam"))
    monkeypatch.setattr(queue_store, "_application_day", lambda timezone_name=None: (local.date().isoformat(), local))


def test_atomic_daily_reservations_enforce_limit_and_deduplicate(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    assert queue_store.reserve_daily_slot("lead-1", 10)
    assert not queue_store.reserve_daily_slot("lead-1", 10)
    for number in range(2, 11):
        assert queue_store.reserve_daily_slot(f"lead-{number}", 10)
    assert not queue_store.reserve_daily_slot("lead-11", 10)


def test_confirmed_submissions_count_toward_reservations(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)

    for number in range(1, 10):
        lead = {
            "source": "jobicy",
            "title": f"Frontend {number}",
            "url": f"https://example.com/jobs/{number}",
        }
        lead_id = queue_store.enqueue(lead)
        queue_store.set_state(lead_id, "SUBMITTED")

    assert queue_store.submitted_today() == 9
    assert queue_store.reserve_daily_slot("tenth-lead", 10)
    assert not queue_store.reserve_daily_slot("eleventh-lead", 10)


def test_submission_timestamp_survives_later_state_changes(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    lead_id = queue_store.enqueue({
        "source": "jobicy",
        "title": "Frontend",
        "url": "https://example.com/jobs/1",
    })
    queue_store.set_state(lead_id, "SUBMITTED")
    with queue_store._db() as conn:
        submitted_at = conn.execute(
            "SELECT submitted_at FROM leads WHERE id=?", (lead_id,)
        ).fetchone()[0]

    queue_store.set_state(lead_id, "REPLIED")
    with queue_store._db() as conn:
        later_submitted_at = conn.execute(
            "SELECT submitted_at FROM leads WHERE id=?", (lead_id,)
        ).fetchone()[0]

    assert submitted_at == later_submitted_at
