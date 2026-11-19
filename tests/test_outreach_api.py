import app as hunter_app
import queue_store


def test_authenticated_outreach_api_records_categorized_rejection(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.setattr(hunter_app, "_authorized", lambda: True)
    outreach_id = queue_store.save_outreach_drafts([{
        "company": "Example Labs",
        "opportunity_type": "junior_vacancy",
        "vacancy_url": "https://example.test/frontend",
        "message_draft": "draft",
    }])[0]

    client = hunter_app.app.test_client()
    response = client.post(
        f"/outreach/{outreach_id}/status",
        json={"status": "REJECTED", "feedback_reason": "location_restriction"},
    )
    assert response.status_code == 200
    record = queue_store.list_outreach()[0]
    assert record["feedback_reason"] == "location_restriction"

    report = client.get("/outreach")
    assert report.status_code == 200
    assert "Ограничение по локации: 1" in report.get_json()["feedback_report"]


def test_outreach_api_rejects_invalid_reason_and_missing_record(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "api-errors.sqlite"))
    monkeypatch.setattr(hunter_app, "_authorized", lambda: True)
    client = hunter_app.app.test_client()

    invalid = client.post(
        "/outreach/not-found/status",
        json={"status": "REJECTED", "feedback_reason": "made_up"},
    )
    assert invalid.status_code == 400
    missing = client.post(
        "/outreach/not-found/status",
        json={"status": "REJECTED", "feedback_reason": "other"},
    )
    assert missing.status_code == 404


def test_outreach_api_requires_authentication(monkeypatch):
    monkeypatch.setattr(hunter_app, "_authorized", lambda: False)
    response = hunter_app.app.test_client().get("/outreach")
    assert response.status_code == 401
