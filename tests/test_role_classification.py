from hh_web_search import title_matches_category
from profit_ranker import rank_lead


def test_qa_automation_with_javascript_is_not_frontend():
    title = "Junior QA auto / Тестировщик-автоматизатор (JavaScript / TypeScript)"
    lead = rank_lead({
        "title": title,
        "source": "hh",
        "description": "Автотестирование web-приложений",
        "category": "frontend",
    })

    assert not lead["eligible"]
    assert lead["rank_reason"] == "non-target QA role"
    assert not title_matches_category(title, "frontend")
    assert title_matches_category(title, "qa")


def test_react_developer_stays_frontend():
    title = "Junior React Developer (TypeScript)"
    lead = rank_lead({"title": title, "source": "hh", "description": "React"})
    assert lead["category"] == "frontend"
    assert title_matches_category(title, "frontend")
