import re

import pytest

from proposal_writer import make_proposal


@pytest.mark.parametrize(
    "lead",
    [
        {"title": "Junior React Developer", "description": "React TypeScript Redux REST API"},
        {"title": "Junior верстальщик", "description": "адаптивная верстка SCSS"},
        {"title": "Junior QA", "category": "qa", "language": "ru"},
        {"title": "Junior Frontend Developer", "language": "en", "description": "React"},
        {"title": "Junior Frontend", "description": "SQL required"},
    ],
)
def test_generated_drafts_do_not_invent_quantified_impact(lead):
    draft = make_proposal(lead)
    assert not re.search(r"\\b\\d+(?:[.,]\\d+)?\\s*%", draft)
    assert not re.search(
        r"(?i)(?:increased revenue|reduced bugs|improved uptime|"
        r"снизил(?:а)? количество ошибок|увеличил(?:а)? выручку|"
        r"повысил(?:а)? отказоустойчивость|ускорил(?:а)? на\\s*\\d)",
        draft,
    )


@pytest.mark.parametrize(
    "lead",
    [
        {"title": "Junior React Developer", "description": "React Redux", "language": "ru"},
        {"title": "Junior React Developer", "description": "React Redux", "language": "en"},
    ],
)
def test_generated_drafts_do_not_present_personal_projects_as_commercial_work(lead):
    draft = make_proposal(lead).lower()
    assert "коммерческ" not in draft
    assert "commercial experience" not in draft
    assert "employment at" not in draft
    assert "production experience" not in draft


@pytest.mark.parametrize(
    "lead",
    [
        {
            "title": "Junior Frontend",
            "description": "Required: SQL, Kubernetes, AWS, 99.9% uptime",
            "requirements": "Redux, Python, Docker",
        },
        {
            "title": "Junior верстальщик",
            "description": "Responsive SCSS, Figma required",
        },
    ],
)
def test_vacancy_requirements_never_become_candidate_skill_claims(lead):
    draft = make_proposal(lead).lower()
    for skill in ("sql", "kubernetes", "aws", "redux", "python", "docker", "responsive", "scss", "figma"):
        assert skill not in draft
    assert "99.9%" not in draft
