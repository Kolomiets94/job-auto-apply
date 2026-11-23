import main


class FakeResponse:
    status_code = 200
    headers = {}

    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item>
    <title>Frontend Developer Junior</title>
    <link>https://hh.ru/vacancy/12345</link>
    <pubDate>2026-11-23T10:00:00+03:00</pubDate>
    <description><![CDATA[
      <p>Вакансия компании: Example LLC</p>
      <p>Регион: Москва</p>
      <p>Предполагаемый уровень месячного дохода: от 60 000 ₽</p>
    ]]></description>
  </item>
  <item>
    <title>Senior Frontend Developer</title>
    <link>https://hh.ru/vacancy/12346</link>
    <description><![CDATA[<p>Регион: Москва</p>]]></description>
  </item>
  <item>
    <title>Frontend Developer Junior</title>
    <link>https://evil.example/vacancy/12347</link>
    <description><![CDATA[<p>Регион: Москва</p>]]></description>
  </item>
</channel></rss>"""


def test_hh_rss_search_parses_and_filters_candidates(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return FakeResponse(RSS)

    monkeypatch.setattr(main.requests, "get", fake_get)
    leads = main.hh_rss_search("frontend", "junior frontend")

    assert captured["url"] == "https://hh.ru/search/vacancy/rss"
    assert captured["params"] == {"text": "junior frontend", "schedule": "remote", "area": "113"}
    assert len(leads) == 1
    assert leads[0]["url"] == "https://hh.ru/vacancy/12345"
    assert leads[0]["company"] == "Example LLC"
    assert leads[0]["location"] == "Москва"
    assert leads[0]["salary"] == {
        "from": 60000.0, "to": None, "currency": "RUB", "period": "month"
    }
    assert leads[0]["discovery_method"] == "hh_public_rss"
    assert leads[0]["work_mode"] == ""


def test_hh_search_falls_back_after_anonymous_api_403(monkeypatch):
    monkeypatch.setattr(main, "_HH_API_DISABLED", False)

    def blocked(*args, **kwargs):
        raise main.HHAccessUnavailable("HH API HTTP 403; stop queries")

    monkeypatch.setattr(main, "_hh_search", blocked)
    monkeypatch.setattr(main.requests, "get", lambda *args, **kwargs: FakeResponse(RSS))

    leads = main.hh_search("frontend", "junior frontend")

    assert main._HH_API_DISABLED is True
    assert len(leads) == 1
    assert leads[0]["source"] == "hh"


def test_hh_hybrid_rss_fallback_is_scoped_to_yekaterinburg(monkeypatch):
    monkeypatch.setattr(main, "_HH_API_DISABLED", True)
    monkeypatch.setattr(main, "hh_yekaterinburg_area_id", lambda: "1234")
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(kwargs["params"])
        return FakeResponse(RSS)

    monkeypatch.setattr(main.requests, "get", fake_get)
    main.hh_search_hybrid("frontend", "junior frontend")

    assert captured == {"text": "junior frontend", "area": "1234"}
    assert "schedule" not in captured
