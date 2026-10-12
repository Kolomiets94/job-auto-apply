from unittest.mock import Mock, patch
import freelancehunt_adapter as fh
from application_dispatcher import dispatch
import application_dispatcher as dispatcher
import pytest


def lead():
    return {'source':'freelancehunt','can_api_bid':True,'external_id':'123','title':'Вёрстка лендинга',
            'budget':{'amount':3000,'currency':'RUB'}}


def test_api_dispatch_and_confirmed_response(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.setenv('FREELANCEHUNT_TOKEN','test-token')
    comment = 'Hello\nСтоимость: 3000 RUB. Срок: 3 дн.'
    response = Mock(status_code=201, json=lambda:{'data':{'id':456,'attributes':{'comment':comment}}})
    with patch.object(fh.requests,'post',return_value=response) as post:
        assert dispatch(lead(),'Hello')['status'] == 'SUBMITTED'
    assert post.call_args.kwargs['json']['safe_type'] == 'employer'


def test_plain_http_success_is_not_counted_as_sent(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.setenv('FREELANCEHUNT_TOKEN','test-token')
    with patch.object(fh.requests,'post',return_value=Mock(status_code=200,json=lambda:{})):
        assert dispatch(lead(),'Hello')['status'] == 'NEEDS_CONFIRMATION'


def test_missing_token_is_explicit(monkeypatch):
    monkeypatch.setenv('AUTO_FREELANCE_APPLY','1')
    monkeypatch.delenv('FREELANCEHUNT_TOKEN',raising=False)
    assert dispatch(lead(),'Hello')['reason'] == 'freelancehunt_token_missing'


def test_fl_ru_rss_does_not_mark_every_order_paid():
    from freelance_sources import _entries
    xml = """<rss><channel><item><title>Сверстать лендинг на React</title>
    <description>Нужен React</description>
    <link>https://www.fl.ru/projects/123/test/</link></item></channel></rss>"""
    [project] = _entries(xml, "fl_ru")
    assert project["bid_access_unknown"] is True
    assert project.get("paid_bid") is not True


def test_fl_ru_unknown_bid_access_is_not_misreported_as_paid(monkeypatch):
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "0")
    from application_dispatcher import dispatch
    project = {"source": "fl_ru", "title": "React landing", "url": "https://www.fl.ru/projects/123/test/", "bid_access_unknown": True}
    result = dispatch(project, "I can build this React landing page.")
    assert result["status"] == "NEEDS_CONFIRMATION"
    assert result["reason"] == "no_free_direct_channel"


def test_dispatch_submits_without_telegram_interaction(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with patch.object(dispatcher, "_send_email", return_value=None), \
         patch.object(dispatcher, "dispatch_browser",
                      return_value={"status": "SUBMITTED", "reason": "browser_hh_sent"}) as send:
        result = dispatch({"source": "hh", "title": "Junior React"}, "Draft")
    assert result["status"] == "SUBMITTED"
    send.assert_called_once()


@pytest.mark.parametrize("code", [404, 410])
def test_closed_freelancehunt_project_is_not_reported_as_failed(code, monkeypatch):
    monkeypatch.setenv("AUTO_FREELANCE_APPLY", "1")
    monkeypatch.setenv("FREELANCEHUNT_TOKEN", "test-token")
    with patch.object(fh.requests, "post", return_value=Mock(status_code=code)):
        result = dispatch(lead(), "Hello")
    assert result == {"status": "SKIPPED", "reason": "project_unavailable"}
