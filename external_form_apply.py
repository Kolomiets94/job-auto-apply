"""Conservative Playwright handler for public external application forms.

Only explicit allowlisted hosts are eligible. Unknown questions, uploads,
CAPTCHAs and ambiguous confirmation are never treated as successful sends.
"""
import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from application_schedule import application_time_allowed


def allowed_host(url):
    host = (urlsplit(url).hostname or "").lower()
    allowed = {h.strip().lower() for h in os.getenv("EXTERNAL_APPLY_HOSTS", "").split(",") if h.strip()}
    allowed.update({"jobs.lever.co", "boards.greenhouse.io", "job-boards.greenhouse.io",
                    "apply.workable.com", "jobs.ashbyhq.com", "careers.smartrecruiters.com"})
    parts = urlsplit(url)
    return (parts.scheme == "https" and host in allowed and not parts.username
            and not parts.password and parts.port in (None, 443))


def apply_external(lead, proposal):
    url = str(lead.get("apply_url") or lead.get("url") or "")
    if not allowed_host(url):
        return {"status": "NEEDS_CONFIRMATION", "reason": "external_host_not_allowlisted", "apply_url": url}
    if os.getenv("AUTO_BROWSER_APPLY") != "1":
        return {"status": "SHORTLISTED", "reason": "browser_apply_disabled"}
    name = os.getenv("REMOTE_JOB_NAME", "").strip()
    email = (os.getenv("REMOTE_JOB_EMAIL") or os.getenv("SMTP_USER") or "").strip()
    phone = os.getenv("REMOTE_JOB_PHONE", "").strip()
    if not all((name, email, phone)):
        return {"status": "NEEDS_HUMAN", "reason": "external_identity_missing", "apply_url": url}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=os.getenv("BROWSER_HEADLESS", "1") != "0")
        try:
            page = browser.new_page(locale="ru-RU")
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if page.url.split("/")[2].lower() != urlsplit(url).hostname.lower():
                return {"status": "NEEDS_CONFIRMATION", "reason": "external_redirect", "apply_url": page.url}
            body = (page.locator("body").inner_text(timeout=5000) or "").lower()
            if any(term in body for term in ("captcha", "turnstile", "verify you are human", "проверка безопасности")):
                return {"status": "NEEDS_HUMAN", "reason": "external_security_challenge", "apply_url": url}
            forms = page.locator("form")
            if forms.count() == 1:
                form = forms.first
            else:
                candidates = [
                    forms.nth(index) for index in range(forms.count())
                    if forms.nth(index).locator('input[type="email"], input[name="email"]').count()
                    and forms.nth(index).locator('textarea, input[type="file"]').count()
                ]
                if len(candidates) != 1:
                    return {"status": "NEEDS_CONFIRMATION", "reason": "external_form_ambiguous", "apply_url": url}
                form = candidates[0]
            # Optional uploads and choices need not block a simple application.
            for selector in ('select', 'input[type="radio"]', 'input[type="checkbox"]'):
                controls = form.locator(selector)
                for index in range(controls.count()):
                    control = controls.nth(index)
                    if control.is_visible() and (control.get_attribute("required") is not None or
                                                 control.get_attribute("aria-required") == "true"):
                        return {"status": "NEEDS_CONFIRMATION", "reason": "external_required_choice",
                                "apply_url": url}
            uploads = form.locator('input[type="file"]')
            for index in range(uploads.count()):
                upload = uploads.nth(index)
                category = str(lead.get("category") or "frontend").upper()
                resume_path = os.getenv(category + "_CV_FILE") or os.getenv("RESUME_FILE_FOR_UPLOAD", "")
                if resume_path and os.path.isfile(resume_path):
                    upload.set_input_files(resume_path)
                elif upload.get_attribute("required") is not None:
                    return {"status": "NEEDS_HUMAN", "reason": "external_resume_file_missing",
                            "apply_url": url}
            fields = form.locator('input:not([type="hidden"]):not([type="submit"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]), textarea')
            values = {"name": name, "fullname": name, "full_name": name,
                      "email": email, "phone": phone, "telephone": phone,
                      "message": proposal, "cover_letter": proposal, "coverletter": proposal,
                      "letter": proposal, "coverlettertext": proposal,
                      "github": "https://github.com/Kolomiets94",
                      "github_url": "https://github.com/Kolomiets94",
                      "portfolio": "https://github.com/Kolomiets94",
                      "portfolio_url": "https://github.com/Kolomiets94",
                      "location": "Yekaterinburg, Russia",
                      "current_location": "Yekaterinburg, Russia"}
            filled = set()
            for i in range(fields.count()):
                field = fields.nth(i)
                if not field.is_visible():
                    continue
                kind = (field.get_attribute("type") or "text").lower()
                key = (field.get_attribute("name") or field.get_attribute("id") or "").lower().replace("-", "_")
                if kind == "email":
                    key = "email"
                elif kind == "tel":
                    key = "phone"
                required = field.get_attribute("required") is not None or field.get_attribute("aria-required") == "true"
                if not required and (key not in values or kind not in ("text", "email", "tel", "url")):
                    continue
                if key not in values or kind not in ("text", "email", "tel", "url"):
                    return {"status": "NEEDS_CONFIRMATION", "reason": "external_unknown_field", "apply_url": url}
                field.fill(values[key])
                filled.add("letter" if key in ("message", "cover_letter", "coverletter", "coverlettertext", "letter") else
                           "name" if key in ("name", "fullname", "full_name") else key)
            if not {"name", "email", "letter"}.issubset(filled):
                return {"status": "NEEDS_CONFIRMATION", "reason": "external_required_fields_missing", "apply_url": url}
            submit = form.locator('button[type="submit"], input[type="submit"]')
            if submit.count() != 1:
                return {"status": "NEEDS_CONFIRMATION", "reason": "external_submit_ambiguous", "apply_url": url}
            if not application_time_allowed():
                return {"status": "SKIPPED", "reason": "outside_application_hours"}
            success_phrases = ("thank you for applying", "application submitted", "application received",
                               "отклик успешно отправлен", "спасибо за отклик")
            before_submit = (page.locator("body").inner_text(timeout=5000) or "").lower()
            submit.first.click(timeout=10000)
            page.wait_for_timeout(1500)
            body = (page.locator("body").inner_text(timeout=5000) or "").lower()
            if any(term in body and term not in before_submit for term in success_phrases):
                return {"status": "SUBMITTED", "reason": "external_form_confirmed"}
            return {"status": "NEEDS_CONFIRMATION", "reason": "external_submission_unconfirmed", "apply_url": url}
        except PlaywrightTimeoutError:
            return {"status": "FAILED", "reason": "external_browser_timeout", "apply_url": url}
        finally:
            browser.close()

