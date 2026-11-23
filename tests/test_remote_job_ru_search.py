from unittest.mock import Mock

import job_sources


def test_remote_job_ru_expands_role_first_queries_and_paginates(monkeypatch):
    calls = []

    def fake_response(url, **params):
        calls.append((url, params))
        query = params["search[query]"]
        page = params.get("page", 1)
        if query == "React Frontend разработчик" and page == 1:
            html = (
                '<a href="/vacancy/show/100/react-junior">Junior React Developer</a>'
                '<a href="https://evil.example/vacancy/show/999/bad">Bad host</a>'
            )
        elif query == "React Frontend разработчик" and page == 2:
            html = (
                '<a href="/vacancy/show/100/react-junior">Duplicate title</a>'
                '<a href="/vacancy/show/101/frontend-junior">Junior Frontend Developer</a>'
            )
        elif query == "React Frontend разработчик" and page == 3:
            html = '<a href="/vacancy/show/102/react-intern">React Intern</a>'
        elif query == "Frontend-разработчик" and page == 1:
            html = '<a href="/vacancy/show/103/frontend">Frontend Developer</a>'
        else:
            html = ""
        return Mock(text=html)

    monkeypatch.setattr(job_sources, "response", fake_response)
    leads = job_sources.remote_job_ru()

    assert len(leads) == 4
    assert {lead["url"] for lead in leads} == {
        "https://remote-job.ru/vacancy/show/100/react-junior",
        "https://remote-job.ru/vacancy/show/101/frontend-junior",
        "https://remote-job.ru/vacancy/show/102/react-intern",
        "https://remote-job.ru/vacancy/show/103/frontend",
    }
    assert all(lead["source"] == "remote_job_ru" for lead in leads)
    assert all(lead["language"] == "ru" for lead in leads)
    assert any(params["search[query]"] == "React Frontend разработчик" and params.get("page") == 3
               for _, params in calls)
    assert any(params["search[query]"] == "Frontend-разработчик" and params.get("page") == 2
               for _, params in calls)
    assert all(url == "https://remote-job.ru/search" for url, _ in calls)


def test_remote_job_ru_search_queries_keep_existing_staging_and_layout_terms():
    assert "junior frontend" in job_sources.REMOTE_JOB_RU_QUERIES
    assert "стажер верстальщик" in job_sources.REMOTE_JOB_RU_QUERIES
    assert "практикант верстальщик" in job_sources.REMOTE_JOB_RU_QUERIES
    assert "React Frontend разработчик" in job_sources.REMOTE_JOB_RU_QUERIES
    assert job_sources.REMOTE_JOB_RU_PAGES["React Frontend разработчик"] == 3
