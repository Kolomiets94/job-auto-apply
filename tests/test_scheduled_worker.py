import pytest
import queue_store
import scheduled_tasks
import scheduled_worker


def _isolated_db(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "worker.sqlite3"))


def test_supervised_worker_completes_persisted_task_in_dry_run(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    monkeypatch.setenv("DRY_RUN", "1")
    scheduled_tasks.enqueue_scheduled_task("worker-run")
    calls = []
    assert scheduled_worker.process_one("test-worker", lambda: calls.append("ran")) is True
    assert calls == ["ran"]
    assert scheduled_tasks.scheduled_task_status("worker-run")["status"] == "completed"


def test_supervised_worker_fails_closed_without_dry_run(monkeypatch, tmp_path):
    _isolated_db(monkeypatch, tmp_path)
    monkeypatch.delenv("DRY_RUN", raising=False)
    scheduled_tasks.enqueue_scheduled_task("unsafe-run")
    calls = []
    with pytest.raises(RuntimeError, match="requires DRY_RUN=1"):
        scheduled_worker.process_one("test-worker", lambda: calls.append("ran"))
    assert calls == []
    status = scheduled_tasks.scheduled_task_status("unsafe-run")
    assert status["status"] == "pending"
    assert status["attempts"] == 1
