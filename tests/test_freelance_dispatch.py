from unittest.mock import Mock, patch
import freelancehunt_adapter as fh
from application_dispatcher import dispatch
import application_dispatcher as dispatcher
import pytest


def lead():
    return {'source':'freelancehunt','can_api_bid':True,'external_id':'123','title':'Вёрстка лендинга',
            'budget':{'amount':3000,'currency':'RUB'}}


def test_api_dispatch_is_blocked_for_freelance_even_when_token_exists(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.setenv('FREELANCEHUNT_TOKEN','test-token')
    with patch.object(fh.requests,'post') as post:
        result = dispatch(lead(),'Hello')
    assert result == {'status': 'SKIPPED', 'reason': 'freelance_submission_not_authorized'}
    post.assert_not_called()


def test_plain_http_freelance_submission_is_blocked(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.setenv('FREELANCEHUNT_TOKEN','test-token')
    with patch.object(fh.requests,'post') as post:
        assert dispatch(lead(),'Hello')['status'] == 'SKIPPED'
    post.assert_not_called()


def test_missing_token_does_not_change_freelance_authorization(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.delenv('FREELANCEHUNT_TOKEN',raising=False)
    assert dispatch(lead(),'Hello')['reason'] == 'freelance_submission_not_authorized'


def test_fl_ru_rss_does_not_mark_every_order_paid():
    from freelance_sources import _entries
    xml = """<rss><channel><item><title>Сверстать лендинг на React</title>
    <description>Нужен React</description>
    <link>https://www.fl.ru/projects/123/test/</link></item></channel></rss>"""
    [project] = _entries(xml, "fl_ru")
    assert project["bid_access_unknown"] is True
    assert project.get("paid_bid") is not True


def test_fl_ru_freelance_is_not_submitted_automatically(monkeypatch):
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "1")
    project = {"source": "fl_ru", "title": "React landing", "url": "https://www.fl.ru/projects/123/test/", "bid_access_unknown": True}
    result = dispatch(project, "I can build this React landing page.")
    assert result == {"status": "SKIPPED", "reason": "freelance_submission_not_authorized"}


def test_hh_uses_authenticated_browser_without_telegram_interaction(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch.object(dispatcher, "dispatch_browser",
                      return_value={"status": "SUBMITTED", "reason": "browser_hh_sent"}) as send:
        result = dispatch({"source": "hh", "title": "Junior React"}, "Draft")
    assert result["status"] == "SUBMITTED"
    send.assert_called_once()


@pytest.mark.parametrize("code", [404, 410])
def test_closed_freelancehunt_project_is_not_contacted(code, monkeypatch):
    monkeypatch.setenv("AUTO_FREELANCE_APPLY", "1")
    monkeypatch.setenv("FREELANCEHUNT_TOKEN", "test-token")
    with patch.object(fh.requests, "post") as post:
        result = dispatch(lead(), "Hello")
    assert result == {"status": "SKIPPED", "reason": "freelance_submission_not_authorized"}
    post.assert_not_called()
