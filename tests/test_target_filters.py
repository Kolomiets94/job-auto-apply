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
    assert not rank_lead({**lead, "description": "Paid internship. React"})["eligible"]


def test_required_sql_rejected_and_explicit_optional_sql_allowed():
    base = {"source": "hh", "title": "Junior React Developer", "description": "React TypeScript"}
    assert not rank_lead({**base, "requirements": "SQL required"})["eligible"]
    assert not rank_lead({**base, "requirements": "Знание SQL"})["eligible"]
    assert rank_lead({**base, "requirements": "SQL будет плюсом"})["eligible"]


def test_international_jobs_need_explicit_russia_eligibility():
    base = {"title": "Junior React Developer", "description": "React TypeScript"}
    assert rank_lead({**base, "source": "hh", "location": "Россия"})["eligible"]
    assert rank_lead({**base, "source": "remotive", "location": "Russia"})["eligible"]
    for location in ("Worldwide", "Anywhere", "Global", "Remote"):
        assert not rank_lead({**base, "source": "remotive", "location": location})["eligible"]
    assert rank_lead({**base, "source": "remotive", "location": "Worldwide",
                      "description": "React TypeScript. We accept candidates based in Russia"})["eligible"]
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



def test_junior_title_does_not_override_experience_range():
    base = {"source": "hh", "title": "Junior React Developer", "description": "React TypeScript"}
    for experience in ("3–6 лет", "3-6 лет", "2 года", "от 3 лет", "3 years"):
        result = rank_lead({**base, "experience": experience})
        assert (result["eligible"] if experience in ("2 года",) else not result["eligible"]), experience
    assert rank_lead({**base, "experience": "1–3 года"})["eligible"]


def test_freelance_shortlist_excludes_non_web_design_and_backend_delivery():
    titles = (
        "Верстка макетов книг по готовому шаблону. Фигма и гуглдок",
        "Разработать дизайн лендинга на Tilda",
        "Разработать лендинг с регистрацией и функцией сбора имя + мэйл и выдачи заданий на почту",
    )
    for title in titles:
        assert not rank_lead({"source": "fl_ru", "title": title,
                              "description": "React HTML CSS"})["eligible"], title
    assert rank_lead({"source": "freelancehunt", "title": "Верстка лендинга по Figma",
                      "description": "HTML CSS адаптивная верстка"})["eligible"]


def test_entry_level_layout_without_junior_title():
    base = {"source": "hh", "title": "Верстальщик HTML CSS", "description": "Начинающий специалист, HTML CSS SCSS"}
    assert rank_lead(base)["eligible"]
    assert rank_lead(base)["category"] == "layout"
    assert not rank_lead({**base, "description": "HTML CSS SCSS"})["eligible"]
    assert not rank_lead({**base, "title": "Senior верстальщик HTML CSS"})["eligible"]
    assert not rank_lead({**base, "experience": "от 3 лет"})["eligible"]
    assert not rank_lead({**base, "requirements": "SQL required"})["eligible"]


def test_office_roles_are_excluded_even_in_yekaterinburg():
    base = {"source": "hh", "title": "Junior React Developer офис", "description": "React TypeScript"}
    assert not rank_lead({**base, "location": "Екатеринбург"})["eligible"]
    assert not rank_lead({**base, "location": "Санкт-Петербург"})["eligible"]
    assert not rank_lead({"source": "hh", "title": "Junior QA Engineer", "location": "Екатеринбург", "description": "Работа только в офисе. Manual QA"})["eligible"]


def test_hybrid_roles_are_allowed_only_in_yekaterinburg():
    base = {"source": "hh", "title": "Junior React Developer", "description": "React TypeScript",
            "work_mode": "HYBRID"}
    assert rank_lead({**base, "location": "Екатеринбург"})["eligible"]
    assert not rank_lead({**base, "location": "Москва"})["eligible"]


def test_layout_requires_entry_level_signal_and_rejects_senior_experience():
    base = {"source": "hh", "title": "Верстальщик HTML CSS",
            "description": "Начинающий специалист, HTML CSS SCSS"}
    for exp in ("", "без опыта", "от 1 года"):
        assert rank_lead({**base, "experience": exp})["eligible"], exp
    for exp in ("от 3 лет", "5 лет"):
        assert not rank_lead({**base, "experience": exp})["eligible"], exp


def test_frontend_accepts_0_to_3_but_not_from_3():
    base = {"source": "hh", "title": "Frontend React Developer", "description": "React TypeScript"}
    for exp in ("без опыта", "0–3 года", "от 1 года", "1–3 года"):
        assert rank_lead({**base, "experience": exp})["eligible"], exp
    for exp in ("от 3 лет", "от 4 лет", "4 года"):
        assert not rank_lead({**base, "experience": exp})["eligible"], exp



def test_international_broad_region_requires_explicit_russia_eligibility():
    base = {"source": "remotive", "title": "Junior React Developer",
            "location": "Europe", "work_mode": "REMOTE"}
    assert rank_lead({**base, "description": "React TypeScript. We accept candidates based in Russia"})["eligible"]
    assert not rank_lead({**base, "description": "React TypeScript. Europe-based applicants only"})["eligible"]


def test_russia_residence_is_allowed_but_foreign_only_residence_is_rejected():
    base = {"source": "remotive", "title": "Junior React Developer",
            "location": "Worldwide", "work_mode": "REMOTE"}
    assert rank_lead({**base, "description": "React TypeScript. Applicants must reside in Russia."})["eligible"]
    assert not rank_lead({**base, "description": "React TypeScript. Applicants must reside in the US."})["eligible"]


def test_hybrid_or_office_text_cannot_be_overridden_by_remote_mentions():
    base = {"source": "hh", "title": "Junior React Developer",
            "description": "React TypeScript. Remote-friendly team; hybrid schedule.",
            "location": "Москва"}
    assert not rank_lead(base)["eligible"]

    office = {**base, "description": "React TypeScript. Remote-friendly team, but work in office.",
              "location": "Екатеринбург"}
    assert not rank_lead(office)["eligible"]


def test_explicit_hybrid_mode_wins_over_remote_description():
    lead = {"source": "hh", "title": "Junior React Developer",
            "description": "React TypeScript. Remote team.",
            "work_mode": "HYBRID", "location": "Москва"}
    assert not rank_lead(lead)["eligible"]


def test_salary_floor_has_no_upper_limit_in_ranker():
    base = {"source": "hh", "title": "Junior React Developer",
            "description": "React TypeScript", "work_mode": "REMOTE"}
    assert rank_lead({**base, "salary": {"from": 60000, "to": 120000, "currency": "RUB"}})["eligible"]
    assert not rank_lead({**base, "salary": {"from": 50000, "to": 120000, "currency": "RUB"}})["eligible"]
