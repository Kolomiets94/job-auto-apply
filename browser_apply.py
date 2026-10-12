"""Safe browser-based HH.ru application automation."""

import base64
import gzip
import io
import json
import os
import re
from typing import Dict
from application_schedule import application_time_allowed

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

HH_HOSTS = ("hh.ru", "www.hh.ru")
RESUME_TITLES = {
    "frontend": "Frontend-разработчик (React)",
    "layout": "Верстальщик html/css",
    "qa": "Junior QA Engineer",
}


def _enabled():
    return os.getenv("AUTO_BROWSER_APPLY", "0") == "1"


def _looks_like_challenge(page):
    text = (page.locator("body").inner_text(timeout=5000) or "").lower()
    return any(x in text for x in (
        "captcha", "капча", "подтвердите, что вы человек", "проверка безопасности",
        "verify your identity", "security check", "two-factor", "2fa", "код подтверждения",
    ))


def _storage_state(storage_state=None):
    if storage_state:
        return storage_state
    raw = os.getenv("HH_STORAGE_STATE_JSON", "").strip()
    if raw:
        try:
            if raw.startswith("gzip-base64:"):
                compressed = base64.b64decode(raw.removeprefix("gzip-base64:"), validate=True)
                with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                    payload = stream.read(5 * 1024 * 1024 + 1)
                if len(payload) > 5 * 1024 * 1024:
                    raise ValueError("HH session exceeds decompressed size limit")
                return json.loads(payload)
            return json.loads(raw)
        except (ValueError, OSError, EOFError):
            return None
    return os.getenv("HH_STORAGE_STATE", "").strip() or None


def _visible(locator):
    try:
        return locator.is_visible(timeout=700)
    except Exception:
        return False


def _norm(value):
    return re.sub(r"\s+", " ", value or "").strip().lower()


def _confirm_relocation_warning(page):
    button = page.locator('[data-qa="relocation-warning-confirm"]').first
    if _visible(button):
        button.click(timeout=5000)
        page.wait_for_timeout(500)


def _select_resume(page, category):
    """Select and verify the role-specific résumé in HH's current Magritte picker."""
    wanted = RESUME_TITLES.get(category)
    if not wanted:
        return False
    target = _norm(wanted)

    header = page.locator('[data-qa="resume-title"]').first
    if not _visible(header):
        return False

    try:
        if _norm(header.inner_text(timeout=1000)) == target:
            return True
    except Exception:
        pass

    try:
        header.click(timeout=5000)
        page.wait_for_timeout(500)
    except Exception:
        return False

    cards = page.locator('[data-magritte-select-option]')
    for _ in range(8):
        if cards.count():
            break
        page.wait_for_timeout(500)

    chosen = None
    expected = ""
    for i in range(cards.count()):
        card = cards.nth(i)
        try:
            title_node = card.locator('[data-qa="resume-title"]').first
            title = _norm(title_node.inner_text(timeout=700) if title_node.count() else card.inner_text(timeout=700))
            if title and (title == target or target in title or title in target):
                chosen = card
                expected = title
                break
        except Exception:
            continue

    # Older HH layout fallback: title cards without data-magritte-select-option.
    if chosen is None:
        titles = page.locator('[data-qa="resume-title"]')
        for i in range(titles.count()):
            node = titles.nth(i)
            try:
                title = _norm(node.inner_text(timeout=700))
                if title and (title == target or target in title or title in target):
                    chosen = node
                    expected = title
                    break
            except Exception:
                continue

    if chosen is None:
        return False

    try:
        chosen.click(timeout=5000)
        for _ in range(8):
            page.wait_for_timeout(400)
            current = page.locator('[data-qa="resume-title"]').first
            if _visible(current) and _norm(current.inner_text(timeout=700)) == expected:
                return True
    except Exception:
        return False
    return False


def _known_question_answer(question, category):
    """Return only answers grounded in the candidate profile; never guess."""
    q = _norm(question)
    if ("вуз" in q or "университет" in q or "институт" in q) and any(
        x in q for x in ("учитесь", "учишься", "обучени", "проходите обучение", "студент")
    ):
        return "Нет, сейчас не учусь в вузе."
    if ("полной" in q and "частичной" in q and any(
        x in q for x in ("занятост", "работу", "ищете")
    )):
        return "Ищу работу с полной занятостью."
    if category == "qa" and any(x in q for x in ("геймдев", "gamedev", "game dev")) and any(
        x in q for x in ("почему", "интерес", "хотите", "привлека")
    ):
        return "Хочу развиваться в ручном тестировании и применять опыт проверки своих веб-приложений. В геймдеве меня привлекает разнообразие пользовательских сценариев и возможность улучшать качество продукта для пользователей. Готов изучать особенности тестирования игр и начинать с задач уровня Junior."
    if any(x in q for x in ("английск", "english", "уровень языка")):
        return "B1 (Intermediate): читаю техническую документацию и могу базово общаться в команде."
    if any(x in q for x in ("город", "где вы жив", "где прожива", "локац")):
        return "Екатеринбург. Рассматриваю удалённую работу."
    if any(x in q for x in ("ожидания по зарплат", "зарплатные ожидания", "желаемая зарплат", "salary expectation")):
        return "От 60 000 ₽ в месяц для вакансий в России; готов обсуждать условия."
    if any(x in q for x in ("коммерческ", "опыт работы", "сколько лет опыта", "years of experience")):
        return (
            "Коммерческого опыта пока нет. Есть практические проекты: React, TypeScript, "
            "REST API, авторизация, CRUD, валидация, обработка ошибок и адаптивная вёрстка."
        )
    if any(x in q for x in ("react", "typescript", "javascript", "redux", "rest api", "html", "css", "scss")):
        return (
            "Работаю с React, TypeScript, JavaScript ES6+, Redux Toolkit, REST API, "
            "HTML5, CSS3/SCSS, Git, Figma и Vite/Webpack."
        )
    if category == "qa" and any(x in q for x in ("тестирован", "qa", "баг", "bug", "test case", "чек-лист")):
        return (
            "В своих веб-проектах вручную проверял формы, API-интеграции, валидацию "
            "и обработку ошибок. Понимаю клиентскую часть благодаря опыту с React и TypeScript."
        )
    if any(x in q for x in ("удален", "удалён", "remote")):
        return "Да, готов работать удалённо."
    if any(x in q for x in ("когда готовы", "когда можете", "дата выхода", "приступить")):
        return "Готов приступить в ближайшее время."
    return None


def _employer_question_text(field):
    """Read the surrounding question rather than just the input placeholder."""
    try:
        for level in (1, 2, 3, 4, 5):
            parent = field.locator(f"xpath=ancestor::*[self::div or self::fieldset][{level}]")
            if not parent.count():
                continue
            content = _norm(parent.inner_text(timeout=1500))
            if 12 < len(content) <= 350 and content.lower() not in ("писать тут", "ответ", "ваш ответ"):
                return content[:240]
    except Exception:
        pass
    return "question_text_unavailable"


def _answer_known_questions(page, category):
    """Answer free-text employer questions only when a truthful canned answer is known.

    Returns (ok, unanswered_questions). Unknown questions remain untouched and block submit.
    """
    unanswered = []
    fields = page.locator('textarea[name^="task_"], input[name^="task_"]:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])')
    for i in range(fields.count()):
        field = fields.nth(i)
        if not _visible(field):
            continue
        question = _employer_question_text(field)
        answer = _known_question_answer(question, category)
        if not answer:
            unanswered.append(_norm(question)[:180] or "unknown_question")
            continue
        try:
            field.fill(answer)
        except Exception:
            unanswered.append(_norm(question)[:180] or "unfillable_question")

    # Choice questions can materially change eligibility. Do not guess them.
    choice_controls = page.locator('input[name^="task_"][type="radio"], input[name^="task_"][type="checkbox"], select[name^="task_"]')
    for i in range(choice_controls.count()):
        control = choice_controls.nth(i)
        if _visible(control):
            question = _employer_question_text(control)
            normalized = _norm(question)[:180] or "choice_question_text_unavailable"
            if normalized not in unanswered:
                unanswered.append(normalized)

    return not unanswered, unanswered


def _find_letter_area(page):
    selectors = (
        'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
        'textarea[name="letter"]',
        'textarea[name="text"]',
        'textarea[data-qa*="letter"]',
        'textarea[placeholder*="опроводитель"]',
    )
    for _ in range(10):
        for selector in selectors:
            area = page.locator(selector).first
            if _visible(area):
                return area
        toggle = page.locator('[data-qa="vacancy-response-letter-toggle"]').first
        if not _visible(toggle):
            toggle = page.get_by_text("Сопроводительное", exact=False).first
        if _visible(toggle):
            try:
                toggle.click(timeout=3000)
            except Exception:
                pass
        page.wait_for_timeout(500)
    return None


def _verify_response_sent(page, vacancy_url):
    try:
        page.goto(vacancy_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
    except Exception:
        return False
    view = page.locator(
        '[data-qa="vacancy-response-link-view-topic"], [data-qa="vacancy-response-link-view"]'
    ).first
    if _visible(view):
        return True
    body = (page.locator("body").inner_text(timeout=5000) or "").lower()
    return any(x in body for x in (
        "вы откликнулись", "вы уже откликались", "резюме доставлено", "отклик доставлен",
    ))


def _hh_live_filter(page, lead):
    """Recheck live requirements and experience before opening an application."""
    from profit_ranker import rank_lead
    live_lead = {**lead, "source": "hh"}
    for key, selector in (
        ("experience", '[data-qa="vacancy-experience"]'),
        ("description", '[data-qa="vacancy-description"]'),
    ):
        field = page.locator(selector).first
        if _visible(field):
            live_lead[key] = field.inner_text(timeout=5000)
    return rank_lead(live_lead)


def apply_hh(lead: Dict, proposal: str, storage_state=None) -> Dict[str, str]:
    raw_url = str(lead.get("url") or "")
    if not raw_url:
        return {"status": "SKIPPED", "reason": "missing_url"}
    if not any(host in raw_url for host in HH_HOSTS):
        return {"status": "SKIPPED", "reason": "unsupported_browser_source"}
    if not _enabled():
        return {"status": "SHORTLISTED", "reason": "browser_apply_disabled"}

    state = _storage_state(storage_state)
    if not state:
        return {"status": "NEEDS_HUMAN", "reason": "hh_session_missing"}

    vacancy_url = raw_url.split("?")[0]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("BROWSER_HEADLESS", "1") != "0")
        try:
            context = browser.new_context(storage_state=state, locale="ru-RU")
            page = context.new_page()
            page.goto(vacancy_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)

            if _looks_like_challenge(page):
                return {"status": "NEEDS_HUMAN", "reason": "security_challenge"}

            if _verify_response_sent(page, vacancy_url):
                return {"status": "SKIPPED", "reason": "already_applied_on_hh"}

            suitability = _hh_live_filter(page, lead)
            if not suitability["eligible"]:
                return {"status": "SKIPPED", "reason": "vacancy_outside_filters",
                        "detail": suitability["rank_reason"]}

            respond = page.locator(
                '[data-qa="vacancy-response-link-top"], [data-qa="vacancy-response-link-bottom"]'
            ).first
            if not _visible(respond):
                body = (page.locator("body").inner_text(timeout=5000) or "").lower()
                if "войти" in body or "авториз" in body:
                    return {"status": "NEEDS_HUMAN", "reason": "login_required"}
                return {"status": "SKIPPED", "reason": "respond_button_not_found"}

            # Current HH opens the response modal here; nothing is counted as sent
            # until the explicit submit below and the post-submit verification pass.
            respond.click(timeout=10000)
            page.wait_for_timeout(1200)
            _confirm_relocation_warning(page)

            if _looks_like_challenge(page):
                return {"status": "NEEDS_HUMAN", "reason": "security_challenge"}

            category = str(lead.get("category") or "frontend").lower()
            if not _select_resume(page, category):
                return {"status": "NEEDS_CONFIRMATION", "reason": "matching_resume_selector_not_found"}

            questions_ok, unanswered = _answer_known_questions(page, category)
            if not questions_ok:
                return {
                    "status": "NEEDS_CONFIRMATION",
                    "reason": "unknown_employer_question",
                    "detail": unanswered[0] if unanswered else "unknown_question",
                }

            textarea = _find_letter_area(page)
            if textarea is None:
                return {"status": "NEEDS_CONFIRMATION", "reason": "cover_letter_field_not_found"}
            textarea.fill(proposal)
            if _norm(textarea.input_value()) != _norm(proposal):
                return {"status": "FAILED", "reason": "cover_letter_not_preserved"}

            submit = None
            for selector in (
                '[data-qa="vacancy-response-submit-popup"]',
                '[data-qa="vacancy-response-letter-submit"]',
                '[data-qa="vacancy-response-submit"]',
                'button[data-qa*="response-submit"]',
                'button[type="submit"]:has-text("Откликнуться")',
                'button[type="submit"]:has-text("Отправить")',
            ):
                candidate = page.locator(selector).first
                if _visible(candidate):
                    submit = candidate
                    break
            if submit is None:
                return {"status": "NEEDS_CONFIRMATION", "reason": "submit_button_not_found"}

            if not application_time_allowed():
                return {"status": "SKIPPED", "reason": "outside_application_hours"}
            submit.click(timeout=10000)
            page.wait_for_timeout(1800)
            if _looks_like_challenge(page):
                return {"status": "NEEDS_HUMAN", "reason": "security_challenge"}

            if _verify_response_sent(page, vacancy_url):
                return {"status": "SUBMITTED", "reason": "browser_hh_sent"}
            return {"status": "NEEDS_CONFIRMATION", "reason": "submission_not_confirmed"}

        except PlaywrightTimeoutError:
            return {"status": "FAILED", "reason": "browser_timeout"}
        finally:
            browser.close()




def _remote_job_challenge_pending(page):
    token = page.locator('input[name="add_response[captcha_response]"]')
    return bool(token.count() and not token.first.input_value().strip())


def _remote_job_validation_errors(page):
    # Scope errors to the response form and exclude informational alerts.
    errors = page.locator(
        'form[name="add_response"] .alert-danger, '
        'form[name="add_response"] .invalid-feedback, '
        'form[name="add_response"] .field-error, '
        'form[name="add_response"] .form-error, '
        'form[name="add_response"] .error-message, '
        'form[name="add_response"] input:invalid, '
        'form[name="add_response"] textarea:invalid'
    )
    messages = []
    for i in range(min(errors.count(), 8)):
        node = errors.nth(i)
        if not _visible(node):
            continue
        # validationMessage is a DOM property, not an HTML attribute.
        message = node.evaluate("el => el.validationMessage || el.innerText || ''")
        message = _norm(message)
        # Report field names, never echoed identity values or token contents.
        message = re.sub(r"[^\s@]+@[^\s@]+", "[email]", message)
        message = re.sub(r"\+?\d[\d ()-]{7,}\d", "[phone]", message)
        if message:
            messages.append(message[:180])
    return messages


def apply_remote_job(lead: Dict, proposal: str) -> Dict[str, str]:
    """Submit Remote-job.ru's public response form, failing closed on missing identity or confirmation."""
    raw_url = str(lead.get("url") or "")
    if "remote-job.ru/vacancy/" not in raw_url:
        return {"status": "SKIPPED", "reason": "unsupported_browser_source"}
    if not _enabled():
        return {"status": "SHORTLISTED", "reason": "browser_apply_disabled"}

    name = os.getenv("REMOTE_JOB_NAME", "").strip()
    email = (os.getenv("REMOTE_JOB_EMAIL", "") or os.getenv("SMTP_USER", "")).strip()
    phone = os.getenv("REMOTE_JOB_PHONE", "").strip()
    if not all((name, email, phone)):
        return {"status": "NEEDS_HUMAN", "reason": "remote_job_identity_missing"}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("BROWSER_HEADLESS", "1") != "0")
        try:
            page = browser.new_page(locale="ru-RU")
            page.goto(raw_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(900)
            if _looks_like_challenge(page):
                return {"status": "NEEDS_HUMAN", "reason": "security_challenge"}

            heading = _norm(page.locator("h1").inner_text(timeout=5000))
            if "вакансия не опубликована" in heading:
                return {"status": "SKIPPED", "reason": "vacancy_unavailable"}

            # Some Remote-job.ru entries are aggregator links to other sites,
            # not public forms. Do not treat clicking those links as an application.
            external_link = page.get_by_role("link", name="Откликнуться на вакансию", exact=True).first
            if _visible(external_link):
                href = external_link.get_attribute("href") or ""
                from urllib.parse import urljoin, urlsplit
                destination = urljoin(raw_url, href)
                if urlsplit(destination).hostname not in ("remote-job.ru", "www.remote-job.ru"):
                    from aggregator_origin import is_gorodrabot_advert, apply_origin
                    if is_gorodrabot_advert(destination):
                        return apply_origin({**lead, "apply_url": destination}, proposal, apply_hh)
                    from external_form_apply import apply_external
                    return apply_external({**lead, "apply_url": destination}, proposal)

            # Remote-job.ru hides its public form until the vacancy response
            # button is clicked. Never click the submit button at this stage.
            reveal = page.get_by_role("button", name="Откликнуться на вакансию", exact=True).first
            if not _visible(reveal):
                reveal = page.get_by_text("Откликнуться на вакансию", exact=True).first
            if _visible(reveal):
                reveal.click(timeout=7000)
                page.wait_for_timeout(600)

            # Public response form labels currently shown by Remote-job.ru.
            fields = {
                "name": page.get_by_label("Имя", exact=True).first,
                "email": page.get_by_label("Email", exact=True).first,
                "phone": page.get_by_label("Телефон", exact=True).first,
                "answer": page.get_by_label("Ответ на вакансию", exact=True).first,
            }
            if not all(_visible(fields[x]) for x in ("email", "phone", "answer")):
                return {"status": "NEEDS_CONFIRMATION", "reason": "remote_job_form_not_found"}

            if _visible(fields["name"]):
                fields["name"].fill(name)
            fields["email"].fill(email)
            fields["phone"].fill(phone)
            fields["answer"].fill(proposal)

            # An empty Turnstile response must never be submitted or bypassed.
            if _remote_job_challenge_pending(page):
                return {"status": "NEEDS_HUMAN", "reason": "remote_job_turnstile_required"}

            # Newsletter consent is optional and deliberately left unchecked.
            submit = page.get_by_role("button", name="Отправить отклик", exact=True).first
            if not _visible(submit):
                return {"status": "NEEDS_CONFIRMATION", "reason": "submit_button_not_found"}
            if not application_time_allowed():
                return {"status": "SKIPPED", "reason": "outside_application_hours"}

            submit.click(timeout=10000)
            page.wait_for_timeout(1600)
            if _looks_like_challenge(page):
                return {"status": "NEEDS_HUMAN", "reason": "security_challenge"}

            body = _norm(page.locator("body").inner_text(timeout=5000))
            success_phrases = (
                "отклик отправлен", "отклик успешно отправлен", "спасибо за отклик",
                "ваш отклик отправлен", "отклик оставлен",
            )
            if any(x in body for x in success_phrases):
                return {"status": "SUBMITTED", "reason": "browser_remote_job_sent"}
            # Diagnose the public form without claiming a successful submission.
            # Do not retry an ambiguous send: it could create a duplicate application.
            # Inspect actual HTML constraint failures first. Do not log field values,
            # candidate contact details, or generic site notices as form errors.
            invalid_fields = page.locator('input:invalid, textarea:invalid, select:invalid')
            field_issues = []
            for i in range(min(invalid_fields.count(), 10)):
                node = invalid_fields.nth(i)
                if not _visible(node):
                    continue
                info = node.evaluate("""el => ({
                    field: el.getAttribute('name') || el.getAttribute('type') || el.tagName,
                    reason: el.validity.valueMissing ? 'required' :
                            el.validity.typeMismatch ? 'invalid_format' :
                            el.validity.patternMismatch ? 'pattern_mismatch' :
                            el.validity.tooShort ? 'too_short' :
                            el.validity.tooLong ? 'too_long' : 'invalid'
                })""")
                field_issues.append(str(info["field"])[:50] + ": " + info["reason"])
            if field_issues:
                return {
                    "status": "NEEDS_CONFIRMATION",
                    "reason": "remote_job_form_validation_error",
                    "detail": "; ".join(field_issues)[:350],
                }
            validation_errors = _remote_job_validation_errors(page)
            if validation_errors:
                return {
                    "status": "NEEDS_CONFIRMATION",
                    "reason": "remote_job_form_validation_error",
                    "detail": "; ".join(validation_errors)[:350],
                }
            # Never infer success from a click alone.
            return {"status": "NEEDS_CONFIRMATION", "reason": "submission_not_confirmed"}
        except PlaywrightTimeoutError:
            return {"status": "FAILED", "reason": "browser_timeout"}
        finally:
            browser.close()


def dispatch_browser(lead: Dict, proposal: str) -> Dict[str, str]:
    from application_links import hh_vacancy_url
    original_hh = hh_vacancy_url(lead.get("apply_url"))
    if original_hh:
        return apply_hh({**lead, "source": "hh", "url": original_hh}, proposal)
    source = str(lead.get("source") or lead.get("site") or "").lower()
    url = str(lead.get("url") or "").lower()
    if "hh" in source or "hh.ru" in url:
        return apply_hh(lead, proposal)
    if source == "remote_job_ru" or "remote-job.ru/vacancy/" in url:
        return apply_remote_job(lead, proposal)
    from external_form_apply import apply_external
    if lead.get("apply_url"):
        return apply_external(lead, proposal)
    return {"status": "SKIPPED", "reason": "unsupported_browser_source"}
