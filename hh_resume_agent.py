"""Read-only HeadHunter resume discovery and review."""
import json
import os
import sys
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from browser_apply import _looks_like_challenge, _storage_state
from hh_resume_review import review_resume_text

HH_RESUMES_URL = "https://hh.ru/applicant/resumes"
HH_HOSTS = {"hh.ru", "www.hh.ru"}


def _safe_hh_url(value):
    parsed = urlparse(value or "")
    return parsed.scheme == "https" and parsed.hostname in HH_HOSTS


def _read_vacancy(page, url):
    if not url:
        return {"status": "not_requested"}
    if not _safe_hh_url(url) or "/vacancy/" not in urlparse(url).path:
        return {"status": "invalid_url"}
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(700)
    if _looks_like_challenge(page):
        return {"status": "security_challenge"}
    if "/account/login" in page.url or "/login" in page.url:
        return {"status": "login_required"}
    title = ""
    for selector in ('[data-qa="vacancy-title"]', "h1"):
        node = page.locator(selector).first
        try:
            if node.count():
                title = " ".join(node.inner_text(timeout=1500).split())
                if title:
                    break
        except Exception:
            continue
    description = ""
    for selector in ('[data-qa="vacancy-description"]', '[data-qa="vacancy-view-description"]'):
        node = page.locator(selector).first
        try:
            if node.count():
                description = node.inner_text(timeout=3000)
                if description:
                    break
        except Exception:
            continue
    return {"status": "read" if title or description else "unrecognized",
            "title": title[:300], "description": description[:20000]}


def inspect_resumes():
    state = _storage_state()
    if not isinstance(state, dict) or not state.get("cookies"):
        return {"status": "missing_session", "resumes": []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(storage_state=state, locale="ru-RU")
            page = context.new_page()
            page.set_default_navigation_timeout(45000)
            page.goto(HH_RESUMES_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            if _looks_like_challenge(page):
                return {"status": "security_challenge", "resumes": []}
            if "/account/login" in page.url or "/login" in page.url:
                return {"status": "login_required", "resumes": []}
            candidates = page.locator('a[href*="/resume/"]')
            found, seen = [], set()
            for index in range(min(candidates.count(), 100)):
                link = candidates.nth(index)
                try:
                    href = link.get_attribute("href") or ""
                    title = " ".join((link.inner_text(timeout=800) or "").split())
                    if not href or not title:
                        continue
                    absolute = urljoin(page.url, href)
                    parsed = urlparse(absolute)
                    if parsed.hostname not in HH_HOSTS or "/resume/" not in parsed.path or absolute in seen:
                        continue
                    seen.add(absolute)
                    found.append({"title": title[:180], "url": absolute})
                except Exception:
                    continue
            if not found:
                body = (page.locator("body").inner_text(timeout=5000) or "").lower()
                if "резюме" not in body:
                    return {"status": "page_unrecognized", "resumes": []}

            vacancy = _read_vacancy(page, os.getenv("HH_TARGET_VACANCY_URL", "").strip())
            reviewed = []
            for resume in found[:30]:
                page.goto(resume["url"], wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(600)
                if _looks_like_challenge(page):
                    resume["review_status"] = "security_challenge"
                    reviewed.append(resume)
                    break
                if "/account/login" in page.url or "/login" in page.url:
                    resume["review_status"] = "login_required"
                    reviewed.append(resume)
                    break
                try:
                    full_text = page.locator("body").inner_text(timeout=7000)
                    resume.update(review_resume_text(full_text, vacancy))
                    resume["review_status"] = "read"
                except Exception:
                    resume["review_status"] = "read_failed"
                reviewed.append(resume)
            return {
                "status": "authenticated", "resume_count": len(found),
                "reviewed_count": sum(r.get("review_status") == "read" for r in reviewed),
                "vacancy_review": {k: v for k, v in vacancy.items() if k != "description"},
                "resumes": reviewed,
                "note": "Read-only. Full resume text is confidential report data; no HH fields were changed and no applications were sent.",
            }
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        result = inspect_resumes()
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] != "authenticated":
            sys.exit(2)
    except Exception as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        sys.exit(1)
