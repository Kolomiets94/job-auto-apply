import json

import browser_apply


def test_hh_apply_disabled_by_default(monkeypatch):
    monkeypatch.delenv("AUTO_BROWSER_APPLY", raising=False)
    result = browser_apply.apply_hh(
        {"url": "https://hh.ru/vacancy/123"},
        "hello",
    )
    assert result == {"status": "SHORTLISTED", "reason": "browser_apply_disabled"}


def test_non_hh_url_is_skipped(monkeypatch):
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "1")
    result = browser_apply.apply_hh(
        {"url": "https://example.com/job"},
        "hello",
    )
    assert result["reason"] == "unsupported_browser_source"


def test_storage_state_from_json_secret(monkeypatch):
    state = {"cookies": [{"name": "x", "value": "1", "domain": ".hh.ru", "path": "/"}], "origins": []}
    monkeypatch.setenv("HH_STORAGE_STATE_JSON", json.dumps(state))
    assert browser_apply._storage_state() == state


def test_invalid_storage_state_json_is_ignored(monkeypatch):
    monkeypatch.setenv("HH_STORAGE_STATE_JSON", "{not-json")
    assert browser_apply._storage_state() is None


def test_remote_job_requires_name_and_email(monkeypatch):
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "1")
    monkeypatch.delenv("REMOTE_JOB_NAME", raising=False)
    monkeypatch.delenv("REMOTE_JOB_EMAIL", raising=False)
    monkeypatch.delenv("REMOTE_JOB_PHONE", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    result = browser_apply.apply_remote_job(
        {"source": "remote_job_ru", "url": "https://remote-job.ru/vacancy/show/123/test"},
        "Здравствуйте!",
    )
    assert result == {"status": "NEEDS_HUMAN", "reason": "remote_job_identity_missing"}


def test_remote_job_is_routed_to_browser_handler(monkeypatch):
    calls = []
    def fake_apply(lead, proposal):
        calls.append((lead, proposal))
        return {"status": "NEEDS_CONFIRMATION", "reason": "remote_job_form_not_found"}
    monkeypatch.setattr(browser_apply, "apply_remote_job", fake_apply)
    lead = {"source": "remote_job_ru", "url": "https://remote-job.ru/vacancy/show/123/test"}
    result = browser_apply.dispatch_browser(lead, "Письмо")
    assert result["reason"] == "remote_job_form_not_found"
    assert calls == [(lead, "Письмо")]


def test_remote_job_requires_phone_before_browser_launch(monkeypatch):
    monkeypatch.setenv("AUTO_BROWSER_APPLY", "1")
    monkeypatch.setenv("REMOTE_JOB_NAME", "Applicant")
    monkeypatch.setenv("REMOTE_JOB_EMAIL", "applicant@example.org")
    monkeypatch.delenv("REMOTE_JOB_PHONE", raising=False)
    result = browser_apply.apply_remote_job(
        {"source": "remote_job_ru", "url": "https://remote-job.ru/vacancy/show/123/test"},
        "Hello",
    )
    assert result == {"status": "NEEDS_HUMAN", "reason": "remote_job_identity_missing"}


def test_hh_university_enrollment_question_answer():
    question = "Вы сейчас проходите обучение в вузе? Если да, какая форма обучения (очная/заочная; дневная/вечерняя)?"
    assert browser_apply._known_question_answer(question, "qa") == "Нет, сейчас не учусь в вузе."


def test_hh_unrelated_employer_question_remains_unanswered():
    assert browser_apply._known_question_answer("Какой у вас любимый цвет?", "qa") is None


def test_hh_full_time_employment_question_answer():
    question = "Вы ищете работу с полной или частичной занятостью?"
    assert browser_apply._known_question_answer(question, "qa") == "Ищу работу с полной занятостью."


def test_hh_gamedev_motivation_authorized_by_candidate():
    question = "Почему вы хотите работать в геймдеве? писать тут"
    answer = browser_apply._known_question_answer(question, "qa")
    assert answer and "своих веб-приложений" in answer
    assert browser_apply._known_question_answer("Какой у вас коммерческий опыт в геймдеве?", "qa").startswith("Коммерческого опыта пока нет.")
    assert browser_apply._known_question_answer("Почему вы хотите работать в геймдеве?", "frontend") is None


def test_choice_question_reads_outer_container_when_nearest_is_empty():
    from unittest.mock import Mock
    control = Mock()
    empty = Mock()
    empty.count.return_value = 1
    empty.inner_text.return_value = ""
    outer = Mock()
    outer.count.return_value = 1
    outer.inner_text.return_value = "Готовы ли вы работать с оборудованием в офисе?"
    control.locator.side_effect = lambda selector: empty if selector.endswith("[1]") else outer
    assert browser_apply._employer_question_text(control) == "готовы ли вы работать с оборудованием в офисе?"


def test_unreadable_choice_question_has_nonempty_diagnostic():
    from unittest.mock import Mock, patch
    page = Mock()
    fields = Mock()
    fields.count.return_value = 0
    choices = Mock()
    choices.count.return_value = 1
    page.locator.side_effect = [fields, choices]
    with patch.object(browser_apply, "_visible", return_value=True), patch.object(
        browser_apply, "_employer_question_text", return_value=""
    ):
        ok, unanswered = browser_apply._answer_known_questions(page, "qa")
    assert not ok
    assert unanswered == ["choice_question_text_unavailable"]


def test_hh_live_experience_overrides_search_card():
    from unittest.mock import Mock, patch
    page = Mock()
    experience = Mock()
    experience.inner_text.return_value = "3–6 лет"
    description = Mock()
    description.inner_text.return_value = "Manual QA Linux"
    page.locator.side_effect = lambda selector: Mock(first=experience if selector == '[data-qa="vacancy-experience"]' else description)
    with patch.object(browser_apply, "_visible", return_value=True):
        result = browser_apply._hh_live_filter(page, {"source": "hh", "title": "Junior React Developer",
                                                     "experience": "", "description": "React TypeScript"})
    assert not result["eligible"]
    assert result["rank_reason"] == "experience range above 3 years"


def test_hh_live_requirements_override_search_snippet():
    from unittest.mock import Mock, patch
    page = Mock()
    experience = Mock()
    experience.inner_text.return_value = "Нет опыта"
    description = Mock()
    description.inner_text.return_value = "Manual QA. SQL required."
    page.locator.side_effect = lambda selector: Mock(first=experience if selector == '[data-qa="vacancy-experience"]' else description)
    with patch.object(browser_apply, "_visible", return_value=True):
        result = browser_apply._hh_live_filter(page, {"source": "hh", "title": "Junior QA Engineer",
                                                     "description": "QA"})
    assert not result["eligible"]
    assert result["rank_reason"] == "SQL outside confirmed stack"
