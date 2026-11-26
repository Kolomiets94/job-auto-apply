import app as app_module


def test_scheduled_queue_diagnostics_requires_auth(monkeypatch):
    monkeypatch.setenv("HUNTER_RUN_TOKEN", "test-token")
    client = app_module.app.test_client()
    response = client.get("/health/scheduled-queue")
    assert response.status_code == 401


def test_scheduled_queue_diagnostics_reports_disabled_mode(monkeypatch):
    monkeypatch.setenv("HUNTER_RUN_TOKEN", "test-token")
    monkeypatch.delenv("HUNTER_SCHEDULED_QUEUE_ENABLED", raising=False)
    client = app_module.app.test_client()
    response = client.get(
        "/health/scheduled-queue",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    assert response.get_json()["queue_enabled"] is False
    assert response.get_json()["mode"] == "legacy"


def test_scheduled_queue_diagnostics_redacts_error_and_metadata(monkeypatch):
    monkeypatch.setenv("HUNTER_RUN_TOKEN", "test-token")
    monkeypatch.setenv("HUNTER_SCHEDULED_QUEUE_ENABLED", "1")
    monkeypatch.setattr(
        "scheduled_tasks.scheduled_task_summary",
        lambda limit: {
            "total": 1,
            "status_counts": {"failed": 1},
            "recent_tasks": [{
                "id": "run-1", "status": "failed", "attempts": 5,
                "created_at": "now", "updated_at": "now", "lease_until": None,
                "last_error": "Bearer supersecret token=hidden https://example.test/path",
            }],
        },
    )
    client = app_module.app.test_client()
    response = client.get(
        "/health/scheduled-queue",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status_counts"] == {"failed": 1}
    task = body["recent_tasks"][0]
    assert "supersecret" not in task["last_error"]
    assert "hidden" not in task["last_error"]
    assert "https://example.test" not in task["last_error"]
    assert "worker_id" not in task
    assert "payload" not in task
