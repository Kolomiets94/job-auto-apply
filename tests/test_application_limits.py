from unittest.mock import patch

import worker


def _lead(url="https://hh.ru/vacancy/1"):
    return {
        "source": "hh",
        "category": "frontend",
        "title": "Junior React Developer",
        "description": "React TypeScript",
        "url": url,
        "profit_score": 80,
        "eligible": True,
        "matched_skills": ["react", "typescript"],
    }


def test_skips_already_submitted_lead():
    lead = _lead()
    with patch.object(worker, "collect_all", return_value=[lead]), \
         patch.object(worker, "rank_leads", return_value=[lead]), \
         patch.object(worker, "enqueue", return_value="lead-1"), \
         patch.object(worker, "was_submitted", return_value=True), \
         patch.object(worker, "submitted_today", return_value=0), \
         patch.object(worker, "dispatch") as dispatch:
        result = worker.run()

    assert result["results"][0]["reason"] == "already_submitted"
    assert result["stats"]["duplicate_skipped"] == 1
    dispatch.assert_not_called()


def test_respects_daily_application_limit(monkeypatch):
    monkeypatch.setenv("DAILY_JOB_LIMIT", "10")
    lead = _lead()
    with patch.object(worker, "collect_all", return_value=[lead]), \
         patch.object(worker, "rank_leads", return_value=[lead]), \
         patch.object(worker, "enqueue", return_value="lead-1"), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", return_value=10), \
         patch.object(worker, "dispatch") as dispatch:
        result = worker.run()

    assert result["results"][0]["reason"] == "daily_application_limit"
    assert result["stats"]["daily_limit_skipped"] == 1
    dispatch.assert_not_called()


def test_submitted_result_increments_daily_total(monkeypatch):
    monkeypatch.setenv("DAILY_JOB_LIMIT", "10")
    lead = _lead()
    with patch.object(worker, "collect_all", return_value=[lead]), \
         patch.object(worker, "rank_leads", return_value=[lead]), \
         patch.object(worker, "enqueue", return_value="lead-1"), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", side_effect=[2, 0]), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "dispatch", return_value={"status": "SUBMITTED", "reason": "browser_hh_sent"}):
        result = worker.run()

    assert result["stats"]["submitted_today_total"] == 3


def test_full_jobs_bucket_does_not_block_freelance(monkeypatch):
    monkeypatch.setenv("DAILY_JOB_LIMIT", "10")
    job = _lead()
    freelance = {**_lead("https://freelance.habr.com/tasks/1"), "source": "habr_freelance",
                 "apply_email": "client@example.com"}
    monkeypatch.setenv("AUTO_SEND_EMAIL", "1")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "alex@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test")
    with patch.object(worker, "collect_all", return_value=[job, freelance]), \
         patch.object(worker, "rank_leads", return_value=[job, freelance]), \
         patch.object(worker, "enqueue", side_effect=lambda lead: "freelance-1" if lead["source"] == "habr_freelance" else "job-1"), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", side_effect=[10, 0]), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "dispatch", return_value={"status":"SUBMITTED"}) as send:
        result = worker.run()
    assert send.call_count == 1
    assert result["stats"]["jobs_submitted_today"] == 10
    assert result["stats"]["freelance_submitted_today"] == 1


def test_full_freelance_bucket_does_not_block_jobs():
    job = _lead()
    with patch.object(worker, "collect_all", return_value=[job]), \
         patch.object(worker, "rank_leads", return_value=[job]), \
         patch.object(worker, "enqueue", return_value="job-1"), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", side_effect=[0, 10]), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "dispatch", return_value={"status":"SUBMITTED"}) as send:
        result = worker.run()
    assert send.call_count == 1
    assert result["stats"]["jobs_submitted_today"] == 1
    assert result["stats"]["freelance_submitted_today"] == 10


def test_zero_limits_do_not_cap_hourly_or_daily_submissions(monkeypatch):
    for name in ("DAILY_JOB_LIMIT", "DAILY_FREELANCE_LIMIT",
                 "HOURLY_JOB_LIMIT", "HOURLY_FREELANCE_LIMIT"):
        monkeypatch.setenv(name, "0")
    leads = [_lead(f"https://hh.ru/vacancy/{i}") for i in range(20, 25)]
    with patch.object(worker, "collect_all", return_value=leads), \
         patch.object(worker, "rank_leads", return_value=leads), \
         patch.object(worker, "enqueue", side_effect=lambda lead: "job-" + lead["url"].rsplit("/", 1)[-1]), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", side_effect=[20, 0]), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "dispatch", return_value={"status": "SUBMITTED"}) as send:
        result = worker.run()
    assert send.call_count == 5
    assert result["stats"]["jobs_submitted_today"] == 25
    assert result["stats"]["daily_limit_skipped"] == 0
    assert result["stats"]["hourly_limit_skipped"] == 0
    assert result["stats"]["daily_job_limit"] is None
    assert result["stats"]["hourly_job_limit"] is None
