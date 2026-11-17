from job_matcher import JobMatcher
from profit_ranker import rank_lead


def test_score_lead_matches_frontend_resume():
    matcher = JobMatcher()
    resume = "Junior Frontend Developer React TypeScript JavaScript HTML CSS SCSS Redux REST Git Figma"
    lead = {
        "title": "Junior React TypeScript Frontend Developer",
        "description": "React, TypeScript, HTML, CSS, REST API",
        "experience": "1-3 года",
    }

    scored = matcher.score_lead(lead, resume)

    assert scored["match_score"] >= 60
    assert "react" in [x.lower() for x in scored["resume_skills_match"]]
    assert scored["match_reason"]


def test_score_lead_without_resume_is_non_blocking():
    matcher = JobMatcher()
    lead = {"title": "React Developer", "description": "React TypeScript"}

    scored = matcher.score_lead(lead, "")

    assert scored["match_score"] is None
    assert scored["match_reason"] == "resume_not_configured"


def test_ranker_rewards_resume_fit():
    base = {
        "title": "Junior Frontend React TypeScript",
        "description": "React TypeScript HTML CSS landing",
        "budget": 30000,
        "work_mode": "REMOTE",
    }

    weak = rank_lead({**base, "match_score": 20})
    strong = rank_lead({**base, "match_score": 90})

    assert strong["profit_score"] > weak["profit_score"]
