import job_sources


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_jobicy_uses_keyword_search_and_normalizes_current_api(monkeypatch):
    calls = []

    def fake_response(url, **params):
        calls.append((url, params))
        return _Response({
            "jobs": [{
                "jobTitle": "Junior React Developer",
                "url": "https://jobicy.com/jobs/123-junior-react",
                "jobDescription": "Remote frontend role. Applicants in Russia are eligible.",
                "jobGeo": "Worldwide",
                "jobLevel": "Entry",
                "jobType": ["Full-Time"],
                "pubDate": "2026-11-22T10:00:00+00:00",
                "salaryMin": 50000,
                "salaryMax": 70000,
                "salaryCurrency": "RUB",
                "salaryPeriod": "Monthly",
            }]
        })

    monkeypatch.setattr(job_sources, "response", fake_response)
    leads = job_sources.jobicy()

    assert [params["tag"] for _, params in calls] == [
        "react", "frontend", "typescript", "html css"
    ]
    assert all(url == "https://jobicy.com/api/jobs" for url, _ in calls)
    assert len(leads) == 1
    assert leads[0]["title"] == "Junior React Developer"
    assert leads[0]["experience"] == "Entry"
    assert leads[0]["location"] == "Worldwide"
    assert leads[0]["salary"]["from"] == 50000


def test_remotive_uses_documented_keyword_search_and_deduplicates(monkeypatch):
    calls = []

    def fake_response(url, **params):
        calls.append((url, params))
        return _Response({
            "jobs": [{
                "title": "Junior Frontend Developer",
                "url": "https://remotive.com/remote-jobs/software-dev/123",
                "description": "React and TypeScript",
                "company_name": "Example",
                "candidate_required_location": "Worldwide",
                "publication_date": "2026-11-22",
            }]
        })

    monkeypatch.setattr(job_sources, "response", fake_response)
    leads = job_sources.remotive()

    assert [params["search"] for _, params in calls] == ["react", "frontend"]
    assert len(leads) == 1
    assert leads[0]["source"] == "remotive"
