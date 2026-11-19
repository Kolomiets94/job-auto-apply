import app as hunter_app


def test_register_telegram_webhook_requires_hunter_auth(monkeypatch):
    monkeypatch.setenv("HUNTER_RUN_TOKEN", "private-token")
    client = hunter_app.app.test_client()
    response = client.post("/telegram/register-webhook")
    assert response.status_code == 401


def test_register_telegram_webhook_uses_server_side_credentials(monkeypatch):
    monkeypatch.setenv("HUNTER_RUN_TOKEN", "private-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "x" * 40)
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True, "result": True}

    def fake_post(url, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    import requests
    monkeypatch.setattr(requests, "post", fake_post)
    client = hunter_app.app.test_client()
    response = client.post(
        "/telegram/register-webhook",
        headers={"Authorization": "Bearer private-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "registered"
    assert captured["url"] == "https://api.telegram.org/botbot-secret/setWebhook"
    assert captured["json"]["url"] == "https://job-freelance-hunter.onrender.com/telegram/webhook"
    assert captured["json"]["secret_token"] == "x" * 40
    assert "bot-secret" not in response.get_data(as_text=True)
    assert "x" * 40 not in response.get_data(as_text=True)
