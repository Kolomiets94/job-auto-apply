from ats_evaluator import build_market_report, review_lead


RESUME = (
    "Junior Frontend Developer. React, TypeScript, JavaScript, Redux Toolkit, "
    "REST API, HTML, CSS. Personal project work since August 2024 with CRUD, "
    "authentication, protected routes and validation. English B1."
)


def test_review_lead_exposes_structured_gap_flags():
    lead = {
        "title": "Junior React Frontend Developer",
        "description": "React, TypeScript, Node.js. Commercial experience required.",
        "experience": "От 1 года",
        "key_skills": ["React", "TypeScript", "Node.js"],
    }

    reviewed = review_lead(lead, RESUME)

    assert reviewed["ats_method"] == "transparent_heuristic_v1"
    assert "node.js" in reviewed["ats_missing_keywords"]
    assert reviewed["ats_experience_gap"] is True
    assert reviewed["ats_commercial_gap"] is True
    assert reviewed["ats_project_evidence"] is True
    assert reviewed["ats_role_match"] is True


def test_market_report_aggregates_reasons_and_actions():
    lead = review_lead(
        {
            "title": "Junior React Frontend Developer",
            "description": "React, TypeScript, Node.js. Commercial experience required.",
            "experience": "От 1 года",
            "key_skills": ["React", "TypeScript", "Node.js"],
        },
        RESUME,
    )

    report = build_market_report([lead])

    assert "Вакансий проанализировано: 1" in report
    assert "Не хватает технологий или навыков" in report
    assert "Требуется больший стаж" in report
    assert "Работодатель просит коммерческий опыт" in report
    assert "Что сделать:" in report
    assert "не гарантия отказа" in report
    assert "ПЛАН ДЕЙСТВИЙ:" in report
    assert "Можно исправить сразу:" in report
    assert "Нужно подтвердить проектом:" in report
    assert "Нужно освоить дополнительно:" in report


def test_market_report_handles_empty_batch():
    assert "нет вакансий" in build_market_report([])
