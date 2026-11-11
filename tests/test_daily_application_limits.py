from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import queue_store


def _use_temp_db(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "queue.sqlite3"))
    local = datetime.now(ZoneInfo("Europe/Amsterdam"))
    monkeypatch.setattr(
        queue_store,
        "_application_day",
        lambda timezone_name=None: (local.date().isoformat(), local),
    )


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


def test_concurrent_reservations_never_exceed_daily_cap(monkeypatch, tmp_path):
    _use_temp_db(monkeypatch, tmp_path)
    limit = 10

    def reserve(number):
        return queue_store.reserve_daily_slot(f"parallel-lead-{number}", limit)

    with ThreadPoolExecutor(max_workers=20) as pool:
        outcomes = list(pool.map(reserve, range(40)))

    assert sum(outcomes) == limit
    with queue_store._db() as conn:
        reserved = conn.execute(
            "SELECT COUNT(*) FROM daily_application_reservations"
        ).fetchone()[0]
    assert reserved == limit


def test_postgres_advisory_lock_query_uses_psycopg_placeholders():
    class FakeCursor:
        def execute(self, sql, params):
            self.sql = sql
            self.params = params

    class FakeConnection:
        def cursor(self, row_factory=None):
            self.last_cursor = FakeCursor()
            return self.last_cursor

    raw = FakeConnection()
    connection = queue_store._PgConnection(raw)
    day = "2026-11-11"

    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtext(?))",
        (day,),
    )

    assert raw.last_cursor.sql == (
        "SELECT pg_advisory_xact_lock(hashtext(%s))"
    )
    assert raw.last_cursor.params == (day,)
