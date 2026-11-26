import sqlite3
from datetime import datetime, timedelta, timezone

import queue_store
import scheduled_tasks as tasks


def _db_path(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "tasks.sqlite3"))


def test_enqueue_is_idempotent_and_status_is_read_only(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    assert tasks.enqueue_scheduled_task("run-1", {"source": "workflow_dispatch"}) is True
    assert tasks.enqueue_scheduled_task("run-1", {"source": "duplicate"}) is False
    status = tasks.scheduled_task_status("run-1")
    assert status["status"] == "pending"
    assert status["attempts"] == 0


def test_claim_and_complete_task(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    tasks.enqueue_scheduled_task("run-2", {"safe": True})
    claimed = tasks.claim_scheduled_task(worker_id="worker-a")
    assert claimed == {
        "id": "run-2", "payload": {"safe": True}, "attempts": 1,
        "worker_id": "worker-a",
    }
    assert tasks.claim_scheduled_task(worker_id="worker-b") is None
    assert tasks.finish_scheduled_task("run-2", "worker-b") is False
    assert tasks.finish_scheduled_task("run-2", "worker-a") is True
    assert tasks.scheduled_task_status("run-2")["status"] == "completed"


def test_expired_lease_is_reclaimed_after_worker_crash(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    tasks.enqueue_scheduled_task("run-3")
    first = tasks.claim_scheduled_task(worker_id="worker-a", lease_seconds=30)
    assert first["attempts"] == 1

    expired = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    with queue_store._db() as connection:
        connection.execute(
            "UPDATE hunter_run_tasks SET lease_until=? WHERE id=?",
            (expired, "run-3"),
        )

    second = tasks.claim_scheduled_task(worker_id="worker-b")
    assert second["id"] == "run-3"
    assert second["attempts"] == 2
    assert second["worker_id"] == "worker-b"
    assert tasks.finish_scheduled_task("run-3", "worker-a") is False


def test_failure_retries_then_becomes_terminal(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    tasks.enqueue_scheduled_task("run-4")
    for attempt in range(1, tasks.MAX_ATTEMPTS + 1):
        claimed = tasks.claim_scheduled_task(worker_id=f"worker-{attempt}")
        assert claimed["attempts"] == attempt
        assert tasks.fail_scheduled_task("run-4", f"worker-{attempt}", "temporary failure")
    status = tasks.scheduled_task_status("run-4")
    assert status["status"] == "failed"
    assert status["attempts"] == tasks.MAX_ATTEMPTS
    assert status["last_error"] == "temporary failure"


def test_task_ids_are_validated(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    import pytest
    with pytest.raises(ValueError):
        tasks.enqueue_scheduled_task("")
    with pytest.raises(ValueError):
        tasks.enqueue_scheduled_task("x" * 201)


def test_summary_reports_counts_and_recent_metadata_without_payload(monkeypatch, tmp_path):
    _db_path(monkeypatch, tmp_path)
    tasks.enqueue_scheduled_task("summary-1", {"private": "do-not-return"})
    tasks.enqueue_scheduled_task("summary-2")
    claimed = tasks.claim_scheduled_task(worker_id="private-worker-id")
    assert claimed["id"] == "summary-1"
    summary = tasks.scheduled_task_summary(limit=1)
    assert summary["total"] == 2
    assert summary["status_counts"] == {"pending": 1, "running": 1}
    assert len(summary["recent_tasks"]) == 1
    assert "payload" not in summary["recent_tasks"][0]
    assert "worker_id" not in summary["recent_tasks"][0]
