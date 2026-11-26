import telegram_control
import queue_store
import app as hunter_app


def _update(chat_id, text):
    return {"message": {"chat": {"id": chat_id}, "text": text}}


def test_telegram_outreach_command_lists_records(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "telegram.sqlite"))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)
    queue_store.save_outreach_drafts([{
        "company": "Example Labs",
        "opportunity_type": "junior_vacancy",
        "vacancy_url": "https://example.test/jobs/frontend",
    }])

    result = telegram_control.handle_update(_update("12345", "/outreach"))
    assert result["status"] == "replied"
    assert "Example Labs" in sent[0]
    assert "/set" in sent[0]


def test_telegram_set_command_records_status_and_reason(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(queue_store, "DB_PATH", str(tmp_path / "telegram-set.sqlite"))
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)
    outreach_id = queue_store.save_outreach_drafts([{
        "company": "Example Labs",
        "opportunity_type": "junior_vacancy",
        "vacancy_url": "https://example.test/jobs/frontend",
    }])[0]

    result = telegram_control.handle_update(
        _update("12345", f"/set {outreach_id[:12]} REJECTED experience_gap")
    )
    record = queue_store.list_outreach()[0]
    assert result["status"] == "updated"
    assert record["status"] == "REJECTED"
    assert record["feedback_reason"] == "experience_gap"
    assert "недостаточно опыта" in sent[0]


def test_telegram_commands_ignore_other_chats_and_validate_reasons(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)
    assert telegram_control.handle_update(_update("99999", "/help"))["status"] == "ignored"
    assert sent == []
    telegram_control.handle_update(_update("12345", "/set deadbeef REJECTED raw_text"))
    assert "категорий" in sent[0]


def test_telegram_webhook_requires_secret(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "a-long-secret")
    client = hunter_app.app.test_client()
    response = client.post("/telegram/webhook", json={}, headers={
        "X-Telegram-Bot-Api-Secret-Token": "wrong",
    })
    assert response.status_code == 401


def test_telegram_scheduled_queue_command_reports_disabled_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.delenv("HUNTER_SCHEDULED_QUEUE_ENABLED", raising=False)
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)

    result = telegram_control.handle_update(_update("12345", "/scheduled_queue"))

    assert result == {"status": "replied", "command": "scheduled_queue"}
    assert "выключена" in sent[0]
    assert "legacy" in sent[0]


def test_telegram_scheduled_queue_command_reports_safe_summary(monkeypatch):
    import scheduled_tasks

    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("HUNTER_SCHEDULED_QUEUE_ENABLED", "1")
    monkeypatch.setattr(
        scheduled_tasks,
        "scheduled_task_summary",
        lambda limit: {
            "total": 3,
            "status_counts": {"pending": 2, "failed": 1},
            "recent_tasks": [
                {"id": "scheduled-run-123456", "status": "pending", "attempts": 0,
                 "payload": {"private": "must-not-leak"}, "worker_id": "internal-worker"},
            ],
        },
    )
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)

    telegram_control.handle_update(_update("12345", "/scheduled_queue"))

    assert "Всего задач: 3" in sent[0]
    assert "pending=2" in sent[0]
    assert "failed=1" in sent[0]
    assert "scheduled-ru" in sent[0]
    assert "must-not-leak" not in sent[0]
    assert "internal-worker" not in sent[0]


def test_telegram_scheduled_queue_command_is_restricted_to_configured_chat(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    sent = []
    monkeypatch.setattr(telegram_control, "_reply", sent.append)

    result = telegram_control.handle_update(_update("99999", "/scheduled_queue"))

    assert result["status"] == "ignored"
    assert sent == []
