from direct_outreach import build_outreach_draft, build_outreach_drafts


def test_builds_personalized_draft_and_never_marks_it_sent():
    lead = {
        "company": "Example Tech",
        "title": "Junior React Developer",
        "url": "https://example.com/jobs/1",
        "matched_skills": ["React", "TypeScript"],
    }
    draft = build_outreach_draft(lead)
    assert draft["company"] == "Example Tech"
    assert "Junior React Developer" in draft["message_draft"]
    assert "React, TypeScript" in draft["message_draft"]
    assert "linkedin.com/search/results/people" in draft["people_search_url"]
    assert draft["sent"] is False


def test_skips_unknown_company_and_deduplicates_companies():
    leads = [
        {"title": "Junior React", "url": "https://example.com/1"},
        {"company": "Acme", "title": "Frontend", "url": "https://example.com/2"},
        {"company": "ACME", "title": "React", "url": "https://example.com/3"},
        {"company": "Beta", "title": "Frontend", "url": "https://example.com/4"},
    ]
    drafts = build_outreach_drafts(leads)
    assert [item["company"] for item in drafts] == ["Acme", "Beta"]
    assert all(item["sent"] is False for item in drafts)
