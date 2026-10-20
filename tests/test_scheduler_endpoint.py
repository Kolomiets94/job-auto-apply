"""A scheduled HTTP call must never bypass draft mode or start twice per hour."""

import sqlite3

import app as service
import queue_store


def test_scheduled_trigger_is_authenticated_draft_only_and_idempotent(monkeypatch, tmp_path):
    path = tmp_path / "scheduled.db"
    monkeypatch.setenv("SCHEDULER_TOKEN", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "configured-for-test")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(queue_store, "_db", lambda: sqlite3.connect(path))

    runs = []
    monkeypatch.setattr(service, "run_worker", lambda: runs.append(True) or {"stats": {"submitted": 0}})

    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(service.threading, "Thread", ImmediateThread)
    client = service.app.test_client()
    assert client.post("/run/scheduled").status_code == 401
    headers = {"Authorization": "Bearer test-secret"}
    assert client.post("/run/scheduled", headers=headers).status_code == 202
    assert client.post("/run/scheduled", headers=headers).json["status"] == "already_started"
    assert runs == [True]

    monkeypatch.setenv("DRY_RUN", "0")
    assert client.post("/run/scheduled", headers=headers).status_code == 409
    assert runs == [True]


def test_scheduled_trigger_requires_persistent_storage(monkeypatch):
    monkeypatch.setenv("SCHEDULER_TOKEN", "test-secret")
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = service.app.test_client().post(
        "/run/scheduled", headers={"Authorization": "Bearer test-secret"}
    )
    assert response.status_code == 503
    assert response.json["error"] == "persistent_database_required"
