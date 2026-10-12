from profit_ranker import rank_lead


def test_excludes_unmatched_frameworks_and_mobile_stacks():
    for stack in ("Vue", "Angular", "Full Stack", "React Native", "Flutter"):
        lead = rank_lead({"source": "hh", "title": "Junior React Developer",
                          "description": "Required: " + stack})
        assert not lead["eligible"], stack


def test_accepts_explicit_one_year_frontend_and_rejects_higher_experience():
    base = {"source": "hh", "title": "Frontend React Developer", "description": "React TypeScript"}
    assert rank_lead({**base, "experience": "от 1 года"})["eligible"]
    assert not rank_lead({**base, "experience": "от 3 лет"})["eligible"]
    assert not rank_lead({**base, "experience": "от 1 года", "title": "Middle Frontend React Developer"})["eligible"]


def test_internship_requires_confirmed_payment():
    lead = {"source": "hh", "title": "Junior React internship", "description": "React"}
    assert not rank_lead(lead)["eligible"]
    assert rank_lead({**lead, "description": "Paid internship. React"})["eligible"]


def test_required_sql_rejected_and_explicit_optional_sql_allowed():
    base = {"source": "hh", "title": "Junior React Developer", "description": "React TypeScript"}
    assert not rank_lead({**base, "requirements": "SQL required"})["eligible"]
    assert not rank_lead({**base, "requirements": "Знание SQL"})["eligible"]
    assert rank_lead({**base, "requirements": "SQL будет плюсом"})["eligible"]


def test_russia_and_worldwide_jobs_are_eligible_but_restricted_jobs_are_not():
    base = {"title": "Junior React Developer", "description": "React TypeScript"}
    assert rank_lead({**base, "source": "hh", "location": "Россия"})["eligible"]
    for location in ("Worldwide", "Anywhere", "Global", "Russia"):
        assert rank_lead({**base, "source": "remotive", "location": location})["eligible"]
    assert not rank_lead({**base, "source": "remotive", "location": "US only"})["eligible"]
    assert not rank_lead({**base, "source": "remotive", "location": "Worldwide",
                          "description": "React TypeScript. Must reside in the US"})["eligible"]


def test_junior_web_developer_in_moscow_is_frontend():
    from hh_web_search import title_matches_category
    title = "Младший веб-разработчик — VEDAR"
    assert title_matches_category(title, "frontend")
    lead = {"source": "hh", "title": title, "description": "Москва. HTML CSS React TypeScript", "location": "Москва"}
    result = rank_lead(lead)
    assert result["eligible"]
    assert result["category"] == "frontend"

