import os
from publication_filter import is_new_publication


def test_today_cutoff_uses_yekaterinburg_date(monkeypatch):
    from datetime import datetime, timedelta
    from publication_filter import LOCAL_TZ

    monkeypatch.setenv("MIN_PUBLICATION_DATE", "today")
    today = datetime.now(LOCAL_TZ).date().isoformat()
    yesterday = (datetime.now(LOCAL_TZ).date() - timedelta(days=1)).isoformat()
    assert is_new_publication({"published": today})
    assert not is_new_publication({"published": yesterday})


def test_publication_cutoff(monkeypatch):
    monkeypatch.setenv("MIN_PUBLICATION_DATE", "2026-10-14")
    assert is_new_publication({"published": "2026-10-14T00:00:00+05:00"})
    assert not is_new_publication({"published": "2026-10-13T23:59:00+05:00"})
    assert not is_new_publication({"published": ""})
    assert not is_new_publication({})
    assert not is_new_publication({"published": "unknown"})
    assert is_new_publication({"published": "Wed, 14 Oct 2026 12:00:00 +0500"})
    assert not is_new_publication({"published": "Tue, 13 Oct 2026 12:00:00 +0500"})


def test_publication_timezone(monkeypatch):
    monkeypatch.setenv("MIN_PUBLICATION_DATE", "2026-10-14")
    assert is_new_publication({"published": "2026-10-13T20:00:00Z"})
    assert not is_new_publication({"published": "2026-10-13T18:00:00Z"})
