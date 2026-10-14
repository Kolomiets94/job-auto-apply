from unittest.mock import patch

import worker


def test_collect_all_deduplicates_urls(monkeypatch):
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    same = {"source": "hh", "title": "React Junior", "url": "https://example.com/1"}
    other = {"source": "remoteok", "title": "Frontend", "url": "https://example.com/2"}

    with patch.object(worker, "hh_search", return_value=[same]), \
         patch.object(worker, "remoteok", return_value=[same, other]), \
         patch.object(worker, "collect_freelance", return_value=[]), \
         patch.object(worker, "collect_peopleperhour", return_value=[]), \
         patch.object(worker, "collect_prolinker", return_value=[]), \
             patch.object(worker, "collect_weblancer", return_value=[]), \
             patch.object(worker, "collect_freelancer_com", return_value=[]), \
         patch.object(worker, "collect_freelancehunt", return_value=[]):
        leads = worker.collect_all()

    urls = [lead["url"] for lead in leads]
    assert urls.count("https://example.com/1") == 1
    assert "https://example.com/2" in urls


def test_collect_all_isolates_source_failures(monkeypatch):
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    lead = {"source": "remoteok", "title": "React", "url": "https://example.com/ok"}

    with patch.object(worker, "hh_search", side_effect=RuntimeError("boom")), \
         patch.object(worker, "remoteok", return_value=[lead]), \
         patch.object(worker, "collect_freelance", side_effect=RuntimeError("boom")), \
         patch.object(worker, "collect_peopleperhour", return_value=[]), \
         patch.object(worker, "collect_prolinker", return_value=[]), \
         patch.object(worker, "collect_weblancer", return_value=[]), \
         patch.object(worker, "collect_freelancer_com", return_value=[]), \
         patch.object(worker, "collect_freelancehunt", return_value=[]):
        leads = worker.collect_all()

    assert leads == [lead]


def test_hh_block_without_session_stops_repeated_queries_but_other_sources_continue(monkeypatch):
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    lead = {"source": "remoteok", "title": "Junior React", "url": "https://example.com/job"}
    with patch.object(worker, "hh_search", side_effect=worker.HHAccessUnavailable("HH API HTTP 403; browser session missing")) as hh, \
         patch.object(worker, "remoteok", return_value=[lead]), \
         patch.object(worker, "collect_freelance", return_value=[]), \
         patch.object(worker, "collect_freelancehunt", return_value=[]), \
         patch.object(worker, "collect_weblancer", return_value=[]), \
         patch.object(worker, "collect_freelancer_com", return_value=[]):
        assert worker.collect_all() == [lead]
    assert hh.call_count == 1
    assert len(worker.COLLECTION_ERRORS) == 1


def test_run_keeps_no_email_lead_for_confirmation():
    lead = {
        "source": "test",
        "category": "freelance",
        "title": "React landing page",
        "description": "React TypeScript landing page",
        "url": "https://example.com/project",
        "profit_score": 80,
        "eligible": True,
        "matched_skills": ["react", "typescript"],
    }

    with patch.object(worker, "collect_all", return_value=[lead]), \
         patch.object(worker, "rank_leads", return_value=[lead]), \
         patch.object(worker, "enqueue", return_value="lead-1"), \
         patch.object(worker, "set_state") as set_state:
        result = worker.run()

    assert result["results"][0]["status"] == "NEEDS_CONFIRMATION"
    assert result["results"][0]["reason"] == "no_free_direct_channel"
    set_state.assert_any_call("lead-1", "SHORTLISTED")
    set_state.assert_any_call("lead-1", "NEEDS_CONFIRMATION")


def test_prioritize_actionable_leads(monkeypatch):
    monkeypatch.delenv("FREELANCEHUNT_TOKEN", raising=False)
    leads = [
        {"source": "prolinker_firecrawl", "title": "React project"},
        {"source": "fl_ru", "paid_bid": True, "title": "Paid bid"},
        {"source": "hh", "title": "Junior QA"},
        {"source": "remote_job_ru", "title": "Junior frontend"},
        {"source": "jobicy", "apply_email": "jobs@example.com", "title": "Junior React"},
        {"source": "prolinker_firecrawl", "title": "Email project", "apply_email": "client@example.com"},
    ]
    prioritized = worker.prioritize_actionable_leads(leads)
    assert [x["title"] for x in prioritized] == [
        "Junior React", "Junior frontend", "Junior QA", "React project",
        "Email project", "Paid bid",
    ]


def test_freelancehunt_api_priority_requires_token(monkeypatch):
    lead = {"source": "freelancehunt", "can_api_bid": True}
    monkeypatch.delenv("FREELANCEHUNT_TOKEN", raising=False)
    assert worker._application_priority(lead) == 1
    monkeypatch.setenv("FREELANCEHUNT_TOKEN", "test")
    monkeypatch.setenv("AUTO_FREELANCE_APPLY", "1")
    assert worker._application_priority(lead) == 0


def test_role_priority_is_preserved_over_channel_priority():
    leads = [
        {"source": "hh", "title": "Junior QA Engineer"},
        {"source": "hh", "title": "Junior HTML CSS верстальщик"},
        {"source": "jobicy", "title": "Junior Frontend Developer"},
        {"source": "hh", "title": "Junior React Developer"},
    ]
    result = worker.prioritize_actionable_leads(leads)
    assert [item["title"] for item in result] == [
        "Junior React Developer", "Junior Frontend Developer",
        "Junior HTML CSS верстальщик", "Junior QA Engineer",
    ]


def test_two_challenges_pause_browser_but_allow_email(monkeypatch):
    leads = [
        {"source": "remote_job_ru", "category": "frontend", "title": f"Junior React {i}",
         "url": f"https://remote-job.ru/vacancy/show/{i}/react"} for i in (1, 2, 3)
    ]
    leads.append({"source": "hh", "category": "qa", "title": "Junior Manual QA",
                  "url": "https://hh.ru/vacancy/123"})
    leads.append({"source": "jobicy", "category": "frontend", "title": "Junior React email",
                  "url": "https://jobicy.com/jobs/4", "apply_email": "jobs@example.com"})
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    monkeypatch.setenv("AUTO_APPLY_QA", "1")
    monkeypatch.setattr("lead_enrichment.enrich_lead", lambda lead: lead)
    with patch.object(worker, "collect_all", return_value=leads), \
         patch.object(worker, "queued_leads", return_value=[]), \
         patch.object(worker, "enqueue", side_effect=lambda lead: lead["url"]), \
         patch.object(worker, "rank_leads", return_value=leads), \
         patch.object(worker, "apply_resume_matching", side_effect=lambda items: items), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", return_value=0), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "send_message", return_value={"status": "SENT"}), \
         patch.object(worker, "should_notify", return_value=False), \
         patch.object(worker, "dispatch", side_effect=[
             {"status": "NEEDS_HUMAN", "reason": "remote_job_turnstile_required"},
             {"status": "NEEDS_HUMAN", "reason": "remote_job_turnstile_required"},
             {"status": "SUBMITTED", "reason": "browser_hh_sent"},
             {"status": "SUBMITTED", "reason": "email_sent"},
         ]) as dispatch:
        report = worker.run()
    assert dispatch.call_count == 4
    assert [item["reason"] for item in report["results"]] == [
        "remote_job_turnstile_required", "remote_job_turnstile_required",
        "browser_challenge_pause", "browser_hh_sent", "email_sent",
    ]
    assert report["stats"]["captcha_count"] == 2
    assert report["stats"]["browser_challenge_paused"] == 1
    assert report["stats"]["submitted"] == 2
    assert report["stats"]["paused_browser_hosts"] == ["remote-job.ru"]
    assert report["stats"]["email_submitted_after_browser_pause"] == 1
    assert report["stats"]["paid_placements_ranked"] == 0


def test_draft_run_prepares_letter_without_dispatch_or_state_change(monkeypatch):
    lead = {"source": "hh", "category": "frontend", "title": "Junior React Developer",
            "url": "https://hh.ru/vacancy/1234", "description": "React"}
    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    monkeypatch.setattr("lead_enrichment.enrich_lead", lambda item: item)
    with patch.object(worker, "collect_all", return_value=[lead]), \
         patch.object(worker, "queued_leads", return_value=[]), \
         patch.object(worker, "enqueue", return_value="1234"), \
         patch.object(worker, "rank_leads", return_value=[lead]), \
         patch.object(worker, "apply_resume_matching", side_effect=lambda items: items), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", return_value=0), \
         patch.object(worker, "set_state") as set_state, \
         patch.object(worker, "dispatch") as dispatch, \
         patch.object(worker, "send_message", return_value={"status": "SENT"}):
        report = worker.run()
    assert report["stats"]["submitted"] == 0
    assert report["stats"]["drafted"] == 1
    assert report["results"][0]["status"] == "DRAFT"
    assert "https://github.com/Kolomiets94/" in report["results"][0]["proposal"]
    dispatch.assert_not_called()
    set_state.assert_not_called()


def test_total_hourly_cap_counts_across_job_and_freelance(monkeypatch):
    leads = [
        {"source": "jobicy", "category": "frontend", "title": "Junior React",
         "url": "https://example.com/job", "apply_email": "jobs@example.com"},
        {"source": "freelancehunt", "category": "freelance", "title": "React landing",
         "url": "https://example.com/project", "can_api_bid": True},
    ]
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("HOURLY_TOTAL_LIMIT", "1")
    monkeypatch.setenv("FREELANCEHUNT_TOKEN", "test")
    monkeypatch.setenv("AUTO_FREELANCE_APPLY", "1")
    monkeypatch.setattr(worker, "JOB_COLLECTORS", ())
    monkeypatch.setattr("lead_enrichment.enrich_lead", lambda item: item)
    with patch.object(worker, "collect_all", return_value=leads), \
         patch.object(worker, "queued_leads", return_value=[]), \
         patch.object(worker, "enqueue", side_effect=lambda item: item["url"]), \
         patch.object(worker, "rank_leads", return_value=leads), \
         patch.object(worker, "apply_resume_matching", side_effect=lambda items: items), \
         patch.object(worker, "was_submitted", return_value=False), \
         patch.object(worker, "submitted_today", return_value=0), \
         patch.object(worker, "set_state"), \
         patch.object(worker, "dispatch", return_value={"status": "SUBMITTED", "reason": "email_sent"}) as dispatch, \
         patch.object(worker, "send_message", return_value={"status": "SENT"}):
        report = worker.run()
    assert dispatch.call_count == 1
    assert report["stats"]["submitted"] == 1
    assert report["stats"]["submitted_by_role"]["frontend"] == 1
    assert report["results"][1]["reason"] == "hourly_total_limit"
