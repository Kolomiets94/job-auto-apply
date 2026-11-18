from unittest.mock import Mock, patch

import telegram_notifier
import worker


def test_send_message_disabled_without_env(monkeypatch):
    for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "BOT_TOKEN", "CHAT_ID"):
        monkeypatch.delenv(key, raising=False)

    result = telegram_notifier.send_message("hello")

    assert result["status"] == "DISABLED"


def test_send_message_posts_to_telegram(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True}

    with patch.object(telegram_notifier.requests, "post", return_value=response) as post:
        result = telegram_notifier.send_message("hello", timeout=3)

    assert result["status"] == "SENT"
    post.assert_called_once()
    args, kwargs = post.call_args
    assert "token123" in args[0]
    assert kwargs["json"]["chat_id"] == "42"
    assert kwargs["json"]["text"] == "hello"
    assert kwargs["timeout"] == 3


def test_send_message_supports_legacy_render_env_names(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("BOT_TOKEN", "legacy-token")
    monkeypatch.setenv("CHAT_ID", "legacy-chat")

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True}

    with patch.object(telegram_notifier.requests, "post", return_value=response) as post:
        result = telegram_notifier.send_message("hello")

    assert result == {"status": "SENT", "parts": 1}
    assert "legacy-token" in post.call_args.args[0]
    assert post.call_args.kwargs["json"]["chat_id"] == "legacy-chat"


def test_send_message_rejects_telegram_ok_false(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": False, "description": "chat not found"}

    with patch.object(telegram_notifier.requests, "post", return_value=response):
        try:
            telegram_notifier.send_message("hello")
        except RuntimeError as exc:
            assert "chat not found" in str(exc)
        else:
            raise AssertionError("Telegram API error was not raised")


def test_worker_suppresses_per_vacancy_delivery_in_summary_only_mode():
    notifications = [{"title": "React Job", "message": "test"}]

    result = worker.deliver_notifications(notifications)

    assert result[0]["status"] == "SKIPPED"
    assert result[0]["reason"] == "summary_only_mode"
