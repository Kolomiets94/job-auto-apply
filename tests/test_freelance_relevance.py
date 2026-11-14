from profit_ranker import rank_lead


def test_freelance_frontend_and_layout_tasks_remain_eligible():
    html = rank_lead({
        "source": "fl_ru",
        "title": "HTML верстка",
        "description": "HTML CSS, адаптивная верстка по готовому макету",
    })
    react = rank_lead({
        "source": "freelancer_com",
        "title": "React Booking Flow with Payment",
        "description": "Build a React and TypeScript booking flow",
        "match_score": 30,
    })

    assert html["eligible"], html
    assert react["eligible"], react


def test_design_only_freelance_projects_are_excluded_even_with_frontend_keywords():
    for title in (
        "Дизайн лендинга в фигме",
        "Vibrant Consulting Landing Page Design",
        "Figma Design for a React Website",
    ):
        result = rank_lead({
            "source": "fl_ru",
            "title": title,
            "description": "React, HTML, CSS, website landing page",
        })
        assert not result["eligible"], (title, result)


def test_security_review_is_not_misclassified_as_frontend():
    result = rank_lead({
        "source": "freelancer_com",
        "title": "Security review of web app sign-in, invites and account deletion (TypeScript/Node)",
        "description": "Review React and TypeScript authentication security",
        "match_score": 66,
    })
    assert not result["eligible"]
    assert "security" in result["rank_reason"]


def test_editorial_and_seo_audit_freelance_work_is_excluded():
    for title in (
        "Разработка и верстка женского журнала",
        "Провести аудит сайтов(лендингов)",
        "SEO audit of landing pages",
    ):
        result = rank_lead({
            "source": "fl_ru",
            "title": title,
            "description": "HTML CSS website landing page",
        })
        assert not result["eligible"], (title, result)


def test_generic_website_keyword_alone_does_not_qualify_freelance_task():
    result = rank_lead({
        "source": "freelancer_com",
        "title": "Website project",
        "description": "A website and landing page is needed",
    })
    assert not result["eligible"]
