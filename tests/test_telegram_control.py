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
