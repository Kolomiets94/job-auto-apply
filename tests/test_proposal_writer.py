from proposal_writer import make_proposal


def test_react_letter_uses_verified_project_link_and_four_sentences():
    lead = {"title": "Junior React Developer", "description": "React TypeScript REST API Redux"}
    text = make_proposal(lead)
    assert "VKMarusya" in text
    assert "https://github.com/Kolomiets94/VKMarusya" in text
    assert "Redux Toolkit" in text
    assert "коммерческ" not in text.lower()
    assert text.count(". ") >= 3


def test_layout_letter_links_to_project_without_claiming_figma():
    text = make_proposal({"title": "Junior верстальщик", "description": "адаптивная верстка по Figma"})
    assert "https://github.com/Kolomiets94/travel-blog" in text
    assert "адаптив" in text.lower()
    assert "Figma" not in text


def test_unsupported_vacancy_skill_not_added_to_letter():
    text = make_proposal({"title": "Junior Frontend", "description": "Требуется SQL"})
    assert "SQL" not in text
    assert "https://github.com/Kolomiets94/travel-blog" in text


def test_qa_letter_describes_only_manual_testing_of_own_apps():
    for language in ("ru", "en"):
        text = make_proposal({"title": "Junior QA", "language": language})
        assert "API error handling" not in text
        assert "обработку ошибок API" not in text
        assert "commercial" not in text.lower()
        assert "команде работал" not in text.lower()
