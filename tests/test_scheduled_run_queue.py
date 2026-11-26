import sqlite3
from datetime import datetime, timedelta, timezone

import queue_store
import scheduled_run_queue


def _use_db(monkeypatch, path):
    monkeypatch.setattr(queue_store, "_db", lambda: sqlite3.connect(path))


def test_durable_queue_claims_once_and_reclaims_expired_lease(monkeypatch, tmp_path):
    path = tmp_path / "scheduled.db"
    _use_db(monkeypatch, path)

    assert scheduled_run_queue.enqueue_run("run-1") is True
    assert scheduled_run_queue.enqueue_run("run-1") is False
    assert scheduled_run_queue.claim_next_run() == "run-1"
    assert scheduled_run_queue.claim_next_run() is None

    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE hunter_scheduled_runs SET lease_until=? WHERE id='run-1'",
            (expired,),
        )

    assert scheduled_run_queue.claim_next_run() == "run-1"
    with sqlite3.connect(path) as connection:
        status, attempts = connection.execute(
            "SELECT status, attempts FROM hunter_scheduled_runs WHERE id='run-1'"
        ).fetchone()
    assert status == "running"
    assert attempts == 2


def test_process_run_persists_success_and_failure(monkeypatch, tmp_path):
    path = tmp_path / "scheduled.db"
    _use_db(monkeypatch, path)
    scheduled_run_queue.enqueue_run("success")
    scheduled_run_queue.enqueue_run("failure")
    assert scheduled_run_queue.claim_next_run() == "success"
    assert scheduled_run_queue.claim_next_run() == "failure"

    scheduled_run_queue.process_run("success", lambda **kwargs: {"stats": {"found": 3}})
    scheduled_run_queue.process_run("failure", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with sqlite3.connect(path) as connection:
        rows = dict(connection.execute(
            "SELECT id, status FROM hunter_scheduled_runs"
        ).fetchall())
    assert rows == {"success": "completed", "failure": "failed"}


def test_legacy_rows_are_not_replayed_during_schema_migration(monkeypatch, tmp_path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE hunter_scheduled_runs "
            "(id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT, outcome TEXT)"
        )
        connection.execute(
            "INSERT INTO hunter_scheduled_runs VALUES "
            "('old-complete', '2026-01-01', '2026-01-01', 'completed'), "
            "('old-unknown', '2026-01-02', NULL, NULL)"
        )
    _use_db(monkeypatch, path)

    scheduled_run_queue.ensure_schema()

    with sqlite3.connect(path) as connection:
        rows = dict(connection.execute(
            "SELECT id, status FROM hunter_scheduled_runs"
        ).fetchall())
    assert rows == {"old-complete": "completed", "old-unknown": "abandoned"}
