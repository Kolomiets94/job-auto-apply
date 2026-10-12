"""Search normal HH web pages when the public API rejects the runner."""
import re
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright
from browser_apply import _storage_state, _looks_like_challenge
from entry_level import is_entry_level

JUNIOR = re.compile(r"(?<![a-z])(?:junior|джуниор|джун|младший|младшая)(?![a-zа-я])", re.I)
EXCLUDED = re.compile(r"full[ -]?stack|фул[ -]?ст[еэ]к|middle|senior|lead|junior\s*\+|junior\s+plus", re.I)


def title_matches_category(title, category):
    if not is_entry_level(title) or EXCLUDED.search(title):
        return False
    if category != "qa" and re.search(r"\bqa\b|tester|тестиров|quality assurance|автотест", title, re.I):
        return False
    terms = {
        "frontend": r"front[ -]?end|фронт[ -]?енд|фронт[ -]?энд|react|javascript|typescript|веб-разработчик",
        "layout": r"верст|вёрст|html|css",
        "qa": r"\bqa\b|tester|тестиров|quality assurance",
    }
    return bool(re.search(terms.get(category, r"(?!)"), title, re.I))


def search_hh_web(category, query):
    state = _storage_state()
    if not state:
        raise RuntimeError("HH browser search needs a saved session")
    url = "https://hh.ru/search/vacancy?" + urlencode({
        "text": query, "order_by": "publication_time",
        "items_on_page": "50",
    })
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(storage_state=state, locale="ru-RU")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if _looks_like_challenge(page):
                raise RuntimeError("HH security challenge requires human action")
            if "/account/login" in page.url:
                raise RuntimeError("HH login required")
            try:
                page.locator('[data-qa="serp-item__title"], [data-qa="vacancy-serp__vacancy-title"]').first.wait_for(timeout=10000)
            except Exception:
                body = page.locator("body").inner_text(timeout=5000).lower()
                if "ничего не найдено" in body or "по вашему запросу" in body:
                    return []
                raise RuntimeError("HH search cards not found")
            cards = page.evaluate("""() => Array.from(document.querySelectorAll('[data-qa="serp-item__title"], [data-qa="vacancy-serp__vacancy-title"]')).map(a => {
                const card = a.closest('[class*="vacancy-card--"]') || a.closest('[data-qa="vacancy-serp__vacancy"]') || a.closest('.vacancy-serp-item');
                const details = card ? card.innerText : a.innerText;
                return {title:a.innerText.trim(), url:a.href, description:details.slice(0,4000),
                        remote:details.includes('Можно удалённо'),
                        location:details.includes('Москва') ? 'Москва' : details.includes('Санкт-Петербург') ? 'Санкт-Петербург' : ''};
            })""")
            results = []
            for card in cards:
                title = card.get("title", "")
                if not title_matches_category(title, category):
                    continue
                # Candidate accepts on-site/hybrid work in Moscow and St Petersburg.
                if not card.get("remote") and card.get("location") not in ("Москва", "Санкт-Петербург"):
                    continue
                experience = re.search(r"\b[1-9]\s*[–—-]\s*[1-9]\s*(?:лет|год[а]?)|(?:от|from)\s*\d+\s*(?:лет|год[а]?|years?)", card.get("description", ""), re.I)
                results.append({
                    **card, "source": "hh", "category": category,
                    "experience": experience.group(0) if experience else "",
                    "collection_method": "hh_web",
                })
            return results
        finally:
            browser.close()

