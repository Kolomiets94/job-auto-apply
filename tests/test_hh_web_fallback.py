import worker
from unittest.mock import patch


def test_hh_api_failure_uses_remote_web_fallback(monkeypatch):
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    lead = {
        "source": "hh", "category": "frontend", "title": "Junior+ React Developer",
        "url": "https://hh.ru/vacancy/123", "work_mode": "REMOTE",
    }
    with patch.object(worker, "hh_search", side_effect=worker.HHAccessUnavailable("HTTP 403")), \
         patch.object(worker, "hh_web_session_available", return_value=True), \
         patch.object(worker, "search_hh_web", return_value=[lead]) as web_search, \
         patch.object(worker, "hh_search_hybrid") as hybrid_search, \
         patch.object(worker, "remoteok", return_value=[]):
        leads = worker.collect_all()

    assert leads == [lead]
    assert web_search.call_count == len(worker.QUERIES[:16] + worker.QUERIES[-2:])
    hybrid_search.assert_not_called()


def test_hh_api_failure_skips_web_fallback_without_saved_session(monkeypatch):
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    with patch.object(worker, "hh_search", side_effect=worker.HHAccessUnavailable("HTTP 403")), \
         patch.object(worker, "hh_web_session_available", return_value=False), \
         patch.object(worker, "search_hh_web") as web_search, \
         patch.object(worker, "remoteok", return_value=[]):
        assert worker.collect_all() == []

    web_search.assert_not_called()
    assert any(item["source"] == "hh-web" for item in worker.COLLECTION_ERRORS)
