from hh_resume_review import review_resume_text


def test_review_extracts_full_text_and_detected_skills():
    text = "О себе. Опыт работы. Образование. Ключевые навыки: Python, React, SQL."
    result = review_resume_text(text)
    assert result["full_text"] == text
    assert result["detected_skills"] == ["Python", "React", "SQL"]
    assert result["detected_sections"]["summary"]
    assert result["detected_sections"]["experience"]


def test_review_recommends_missing_sections():
    result = review_resume_text("Python and React")
    assert any("О себе" in item for item in result["recommendations"])
    assert any("образования" in item.lower() for item in result["recommendations"])


def test_vacancy_review_and_draft_use_resume_evidence():
    result = review_resume_text("Навыки: Python, SQL", {
        "status": "read", "title": "Python Developer", "description": "Python, SQL, Docker"})
    assert result["vacancy_match"]["matched_terms"] == ["Python", "SQL"]
    assert result["vacancy_match"]["terms_to_verify"] == ["Docker"]
    assert "Python, SQL" in result["cover_letter_draft"]
    assert "Docker" not in result["cover_letter_draft"]


def test_resume_text_is_bounded():
    assert len(review_resume_text("x" * 60000)["full_text"]) == 50000
