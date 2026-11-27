from proposal_writer import make_proposal


def test_react_letter_uses_verified_project_link_without_unverified_feature_claims():
    text = make_proposal({
        "title": "Junior React Developer",
        "description": "React TypeScript REST API Redux",
    })
    assert "VKMarusya" in text
    assert "https://github.com/Kolomiets94/VKMarusya" in text
    assert "Redux Toolkit" not in text
    assert "TypeScript" not in text
    assert "коммерческ" not in text.lower()
    assert text.count(". ") >= 3


def test_layout_letter_does_not_infer_responsive_or_figma_experience_from_vacancy():
    text = make_proposal({
        "title": "Junior верстальщик",
        "description": "адаптивная верстка по Figma, SCSS",
    })
    assert "https://github.com/Kolomiets94/travel-blog" in text
    assert "адаптив" not in text.lower()
    assert "Figma" not in text
    assert "SCSS" not in text


def test_unsupported_vacancy_skills_are_not_added_to_letter():
    text = make_proposal({
        "title": "Junior Frontend",
        "description": "Требуется SQL, Kubernetes, AWS, Redux",
        "requirements": "Must know Python and Docker",
    })
    for skill in ("SQL", "Kubernetes", "AWS", "Redux", "Python", "Docker"):
        assert skill.lower() not in text.lower()


def test_qa_letter_does_not_invent_specific_testing_experience():
    for language in ("ru", "en"):
        text = make_proposal({
            "title": "Junior QA",
            "category": "qa",
            "language": language,
            "description": "API testing, automation, SQL",
        })
        for claim in ("API testing", "автоматизирован", "SQL", "коммерческ", "commercial experience"):
            assert claim.lower() not in text.lower()
