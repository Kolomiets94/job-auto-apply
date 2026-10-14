from freelance_sources import _parse_freelancer_projects, _parse_weblancer_cards
from publication_filter import is_new_publication


def test_weblancer_cards_have_a_real_publication_date(monkeypatch):
    monkeypatch.setenv("MIN_PUBLICATION_DATE", "2026-10-14")
    html = (
        '<article><h2><a href="https://www.weblancer.net/freelance/css/'
        'landing-123/">Лендинг HTML CSS</a></h2>'
        '<p>Адаптивная вёрстка</p><span>14.10.2026</span></article>'
        '<article><h2><a href="https://www.weblancer.net/freelance/css/'
        'unknown-124/">Вёрстка</a></h2><p>Дата не указана</p></article>'
    )
    leads = _parse_weblancer_cards(html)
    assert len(leads) == 1
    assert is_new_publication(leads[0])
    assert not leads[0].get("can_api_bid")


def test_freelancer_api_projects_remain_discovery_only(monkeypatch):
    monkeypatch.setenv("MIN_PUBLICATION_DATE", "2026-10-14")
    payload = {"status": "success", "result": {"projects": [{
        "status": "active", "title": "Small React layout fix",
        "seo_url": "react-js/small-react-layout-fix",
        "submitdate": 1791961810, "description": "Only CSS and React changes.",
        "preview_description": "Short preview", "language": "en",
    }, {
        "status": "closed", "title": "Old work",
        "seo_url": "css/old-work", "submitdate": 1791961810,
    }]}}
    leads = _parse_freelancer_projects(payload)
    assert len(leads) == 1
    assert is_new_publication(leads[0])
    assert leads[0]["description"] == "Only CSS and React changes."
    assert not leads[0].get("can_api_bid")
