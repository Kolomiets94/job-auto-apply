"""Read-only HeadHunter resume discovery for the GitHub Actions agent.

This first stage deliberately does not modify resumes or submit applications.
The session is supplied only through the HH_STORAGE_STATE_JSON environment secret.
"""
import json
import os
import sys
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

from browser_apply import _looks_like_challenge, _storage_state

HH_RESUMES_URL = "https://hh.ru/applicant/resumes"


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
            found = []
            seen = set()
            for index in range(min(candidates.count(), 100)):
                link = candidates.nth(index)
                try:
                    href = link.get_attribute("href") or ""
                    title = " ".join((link.inner_text(timeout=800) or "").split())
                    if not href or not title:
                        continue
                    absolute = urljoin(page.url, href)
                    parsed = urlparse(absolute)
                    if parsed.hostname not in ("hh.ru", "www.hh.ru"):
                        continue
                    if "/resume/" not in parsed.path or absolute in seen:
                        continue
                    seen.add(absolute)
                    found.append({"title": title[:180], "url": absolute})
                except Exception:
                    continue

            if not found:
                body = (page.locator("body").inner_text(timeout=5000) or "").lower()
                if "резюме" not in body:
                    return {"status": "page_unrecognized", "resumes": []}

            return {
                "status": "authenticated",
                "resume_count": len(found),
                "resumes": found[:30],
                "note": "Read-only inspection. No resume fields were changed.",
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
        # Do not print exception details: browser errors can contain URLs or page data.
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        sys.exit(1)
