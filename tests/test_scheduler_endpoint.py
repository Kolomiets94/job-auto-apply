"""Scheduled and manual HTTP calls must remain draft-only and idempotent."""

import sqlite3

import app as service
import queue_store
import scheduled_run_queue


def _claims(event_name="schedule", run_id="12345", run_attempt="1"):
    return {"event_name": event_name, "run_id": run_id, "run_attempt": run_attempt}


def test_scheduled_trigger_is_authenticated_draft_only_and_idempotent(monkeypatch, tmp_path):
    path = tmp_path / "scheduled.db"
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims())
    monkeypatch.setenv("DATABASE_URL", "configured-for-test")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(queue_store, "_db", lambda: sqlite3.connect(path))
    runs = []

    monkeypatch.setattr(scheduled_run_queue, "start_worker", lambda run_worker: True)
    monkeypatch.setattr(service, "run_worker", lambda: runs.append(True) or {"stats": {}})
    client = service.app.test_client()
    monkeypatch.setattr(service, "_scheduler_claims", lambda: None)
    assert client.post("/run/scheduled").status_code == 401
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims())
    assert client.post("/run/scheduled").status_code == 202
    assert client.post("/run/scheduled").json["status"] == "already_started"
    assert runs == []
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT status, attempts FROM hunter_scheduled_runs"
        ).fetchone()
    assert row == ("queued", 0)
    monkeypatch.setenv("DRY_RUN", "0")
    assert client.post("/run/scheduled").status_code == 409
    assert runs == [True]


def test_manual_dispatch_runs_are_unique_within_same_hour(monkeypatch, tmp_path):
    path = tmp_path / "manual.db"
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims("workflow_dispatch", "9001", "1"))
    monkeypatch.setenv("DATABASE_URL", "configured-for-test")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(queue_store, "_db", lambda: sqlite3.connect(path))
    runs = []

    monkeypatch.setattr(scheduled_run_queue, "start_worker", lambda run_worker: True)
    monkeypatch.setattr(service, "run_worker", lambda: runs.append(True) or {"stats": {}})
    client = service.app.test_client()
    first = client.post("/run/scheduled")
    assert first.status_code == 202
    assert first.json["run_id"] == "9001"
    assert client.post("/run/scheduled").json["status"] == "already_started"
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims("workflow_dispatch", "9002", "1"))
    second = client.post("/run/scheduled")
    assert second.status_code == 202
    assert second.json["run_id"] == "9002"
    assert runs == []
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT id, status FROM hunter_scheduled_runs ORDER BY id"
        ).fetchall()
    assert rows == [("manual:9001:1", "queued"), ("manual:9002:1", "queued")]


def test_manual_dispatch_requires_verified_run_identity(monkeypatch):
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims("workflow_dispatch", "", ""))
    monkeypatch.setenv("DATABASE_URL", "configured-for-test")
    monkeypatch.setenv("DRY_RUN", "1")
    response = service.app.test_client().post("/run/scheduled")
    assert response.status_code == 401
    assert response.json["error"] == "manual_run_identity_missing"


def test_scheduled_trigger_requires_persistent_storage(monkeypatch):
    monkeypatch.setattr(service, "_scheduler_claims", lambda: _claims())
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = service.app.test_client().post("/run/scheduled")
    assert response.status_code == 503
    assert response.json["error"] == "persistent_database_required"
