"""Rank leads by expected profitability and resume fit."""
import re
from typing import Any, Dict

SKILLS = {
    "react": 1.0, "typescript": 1.0, "javascript": .8, "js": .45, "html": .7,
    "css": .7, "scss": .7, "figma": .5, "redux": .7, "redux toolkit": .8,
    "rest api": .6, "vite": .55, "webpack": .55, "git": .4,
    "frontend": .65, "front-end": .65, "верстка": .7, "вёрстка": .7,
    "верстка сайта": .85, "вёрстка сайта": .85, "верстальщик": .85,
    "лендинг": .55, "landing": .55, "адаптив": .5, "сайт": .25,
    "qa": .55, "tester": .55, "тестировщик": .55, "manual qa": .65,
}
BLOCK = (
    "middle", "mid-level", "mid level", "senior", "lead ", "team lead", "tech lead", "head of", "manager", "director", "fullstack", "full stack", "full-stack",
    "react native", "flutter", "angular", "vue.js", "vuejs", "vue 3", "vue 2", "nuxt",
    "node.js required", "internship", "trainee", "стажировка", "стажер", "стажёр",
    "ai engineer", "ai agent engineer", "machine learning engineer", "ml engineer", "security engineer", "security analyst", "cybersecurity",
    "coreldraw", "полиграф", "типограф", "для печати", "визитк",
    "логотип", "illustrator", "интерьер", "3d-модел",
)
RUSSIA_SOURCES = {"hh", "habr_career", "trudvsem", "geekjob", "getmatch", "zarplata", "remote_job_ru", "superjob", "fl_ru", "habr_freelance", "freelancehunt"}
INTERNATIONAL_SOURCES = {"remoteok", "jobicy", "remotive", "weworkremotely", "arbeitnow", "jooble", "peopleperhour", "prolinker", "prolinker_firecrawl", "upwork_frontend"}
FREELANCE_SOURCES = {"fl_ru", "habr_freelance", "freelancehunt", "peopleperhour", "prolinker", "prolinker_firecrawl", "upwork_frontend"}
TARGET_TITLE_TERMS = (
    "frontend", "front-end", "front end", "фронтенд", "фронтэнд", "фронт-енд", "react", "typescript", "javascript",
    "верстальщик", "верстка", "вёрстка", "html", "css", "веб-разработчик",
    "qa tester", "qa engineer", "manual qa", "manual tester",
    "тестировщик", "quality assurance",
)
NON_TARGET_TITLE_TERMS = (
    "architect", "assessor", "annotator", "trainer", "evaluator",
    "data scientist", "data engineer", "product manager", "project manager",
)

# Frameworks and specialties outside the candidate's demonstrated frontend stack.
# Check the project title rather than incidental words in its description.
FREELANCE_TITLE_EXCLUDE = (
    "angular", "mean stack", "knowledge of mean", "ms access", "microsoft access",
    "ui ux designer", "ui/ux designer", "ux designer", "mongodb", "wordpress", "woocommerce",
    "arcgis", "jquery", "drupal", "shopify", "webflow",
    "vue", "nuxt", "svelte", "php", "laravel", "django",
    "magento", "prestashop", "java engineer", "java developer",
    "c# developer", "c# engineer", "blazor", "asp.net",
    "mobile platform", "mobile app", "android", "ios app",
    "full-time", "full time", "webshop", "e-commerce platform",
)

FREELANCE_TOO_COMPLEX = (
    "architect", "архитектор", "devops", "kubernetes", "terraform", "microservices",
    "микросервис", "highload", "high-load", "machine learning", "data engineer",
    "blockchain", "web3", "smart contract", "1c", "bitrix", "битрикс",
    "django", "laravel", "spring boot", ".net", "golang", "rust",
)


def _text(lead: Dict[str, Any]) -> str:
    return " ".join(
        str(lead.get(k) or "")
        for k in ("title", "description", "requirements", "category", "location", "region")
    ).lower()


def _money(lead: Dict[str, Any]) -> float:
    s = lead.get("budget") or lead.get("salary") or ""
    if isinstance(s, dict):
        vals = [x for x in (s.get("from"), s.get("to"), s.get("amount")) if isinstance(x, (int, float))]
        return float(max(vals)) if vals else 0.0
    nums = [
        float(x.replace(" ", "").replace(",", "."))
        for x in re.findall(r"\d[\d ]*(?:[.,]\d+)?", str(s))
    ]
    return max(nums, default=0.0)


def _explicit_salary_rejected(lead: Dict[str, Any]) -> bool:
    if str(lead.get("source") or "").lower() in FREELANCE_SOURCES:
        return False
    salary = lead.get("salary")
    if not salary:
        return False
    source = str(lead.get("source") or "").lower()
    if isinstance(salary, dict):
        currency = str(salary.get("currency") or "").upper()
        vals = [x for x in (salary.get("from"), salary.get("to"), salary.get("amount")) if isinstance(x, (int, float))]
        amount = max(vals) if vals else None
        if amount is None:
            return False
        if currency in ("RUR", "RUB") or source in RUSSIA_SOURCES:
            return amount < 60000
        if currency in ("USD", "$"):
            # RemoteOK-style annual salaries are converted to a monthly comparison.
            period = str(salary.get("period") or "").lower()
            monthly = amount / 12.0 if period in ("year", "yearly", "annual", "annually") else amount
            if not period and source == "remoteok" and amount > 12000:
                monthly = amount / 12.0
            return monthly < 2000
    return False


def _location_rejected(lead: Dict[str, Any], text: str) -> bool:
    # Restrictions override broad promotional worldwide wording.
    restricted = (
        "must reside in", "must be located in", "must live in", "residents only",
        "us only", "u.s. only", "uk only", "eu only", "europe only",
        "right to work in", "work authorization", "work authorisation",
        "visa sponsorship is not available", "no visa sponsorship",
    )
    if any(x in text for x in restricted):
        return True
    if str(lead.get("source") or "").lower() in INTERNATIONAL_SOURCES and str(lead.get("source")) not in FREELANCE_SOURCES:
        location = str(lead.get("location") or "").lower().strip()
        return not any(x in location for x in ("worldwide", "anywhere", "global", "russia", "росси"))
    return False


def _role_category(lead: Dict[str, Any]) -> str:
    """Route jobs to the user's preferred role/resume order."""
    title = str(lead.get("title") or "").lower()
    # QA automation titles may mention JavaScript/TypeScript or React.
    if re.search(r"\bqa\b|tester|тестировщик|тестирование|quality assurance|manual test|автотест", title):
        return "qa"
    # Frontend wins when HTML/CSS also appears in the title.
    if any(x in title for x in ("frontend", "front-end", "front end", "фронтенд", "фронтэнд", "фронт-енд", "react", "typescript", "javascript", "веб-разработчик")):
        return "frontend"
    if any(x in title for x in ("верстальщик", "верстка", "вёрстка", "html", "css")):
        return "layout"
    return str(lead.get("category") or "other").lower()


ROLE_PRIORITY = {"frontend": 0, "layout": 1, "qa": 2}


def rank_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
    text = _text(lead)
    title = str(lead.get("title") or "").lower()
    # Exclude non-Junior roles by title, not incidental descriptions.
    if any(x in title for x in BLOCK) or re.search(r"(?<![a-z])vue(?![a-z])", title):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "excluded job title"}
    if any(x in title for x in ("офис", "onsite", "on-site", "on site", "гибрид", "hybrid")):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "onsite/hybrid job"}
    # Keep mandatory unsupported frameworks excluded, while allowing optional mentions.
    requirements = " ".join(str(lead.get(k) or "") for k in ("description", "requirements")).lower()
    required_parts = re.split(r"[\n.!?;]", requirements)
    optional_markers = ("optional", "nice to have", "nice-to-have", "not required", "необязател", "будет плюсом", "как плюс")
    unsupported = ("vue", "angular", "full stack", "fullstack", "react native", "flutter")
    if any(any(term in part for term in unsupported) and not any(marker in part for marker in optional_markers)
           and any(marker in part for marker in ("required", "must have", "mandatory", "обязательно", "требуется"))
           for part in required_parts):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "mandatory unsupported stack"}
    # SQL is outside the confirmed stack. Clearly optional mentions are allowed.
    sql_parts = re.split(r"[\n.!?;]", text)
    optional_sql = ("optional", "nice to have", "nice-to-have", "not required",
                    "не требуется", "необязател", "будет плюсом", "как плюс")
    if any(re.search(r"\b(?:sql|mysql|postgresql)\b", part) and
           not any(marker in part for marker in optional_sql) for part in sql_parts):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "SQL outside confirmed stack"}
    if _explicit_salary_rejected(lead):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "salary below configured floor"}
    if _location_rejected(lead, text):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "explicit location/work-authorization restriction"}

    source = str(lead.get("source") or "").lower()
    title = str(lead.get("title") or "").lower()
    if source not in FREELANCE_SOURCES:
        if any(x in title for x in NON_TARGET_TITLE_TERMS):
            return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "non-target job title"}
        if not any(x in title for x in TARGET_TITLE_TERMS):
            return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "job title outside target roles"}
        junior_markers = ("junior", "jr.", "jr ", "джуниор", "джун", "младший", "младшая")
        experience = str(lead.get("experience") or "").lower()
        one_year = bool(re.search(r"(?:от|from|at least)\s*1\s*(?:год|года|year)|\b1\s*\+?\s*(?:год|года|year)", experience))
        if not any(x in title for x in junior_markers) and not one_year:
            return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "not Junior or explicitly from one year"}
        if re.search(r"(?:от|from|at least)\s*[2-9]\s*(?:год|года|лет|year)", experience):
            return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "experience above one year"}
        if re.search(r"junior\s*\+|junior\s+plus|джун(?:иор)?\s*\+", title):
            return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "Junior+ excluded"}

    if source in FREELANCE_SOURCES and not any(x in title for x in (
        "react", "typescript", "javascript", "frontend", "front-end", "front end",
        "фронтенд", "html", "css", "верст", "вёрст", "лендинг", "landing",
    )):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "freelance title outside demonstrated stack"}

    if source in FREELANCE_SOURCES and any(x in title for x in FREELANCE_TITLE_EXCLUDE):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "freelance title requires unsupported technology"}

    if source in FREELANCE_SOURCES and any(x in text for x in FREELANCE_TOO_COMPLEX):
        return {**lead, "profit_score": 0, "eligible": False, "rank_reason": "freelance project too complex/out of scope"}

    matched = [k for k in SKILLS if k in text]
    fit = sum(SKILLS[k] for k in matched) / max(sum(SKILLS.values()), 1)
    budget = _money(lead)
    budget_score = (.25 if source in FREELANCE_SOURCES else
                    min(budget / 30000.0, 1.0) if budget else .25)
    quick = .15 if any(x in text for x in ("лендинг", "landing", "верст", "fix", "bug", "правк")) else 0
    competition = lead.get("proposals")
    comp_score = .15 if isinstance(competition, int) and competition < 10 else 0
    resume_match = lead.get("match_score")
    resume_score = (resume_match / 100.0) if isinstance(resume_match, (int, float)) else 0

    score = round(min(100, (fit * .45 + budget_score * .25 + quick + comp_score + resume_score * .25) * 100))
    category = _role_category(lead)
    return {
        **lead,
        "category": category,
        "role_priority": ROLE_PRIORITY.get(category, 99),
        "profit_score": score,
        # One relevant skill is enough to enter the shortlist; safety filters above still apply.
        "eligible": bool(matched) and score >= 8,
        "matched_skills": matched,
        "rank_reason": "role priority + skill fit + budget + speed + competition + resume fit",
    }


def rank_leads(leads):
    ranked = [rank_lead(x) for x in leads]
    eligible = (x for x in ranked if x["eligible"])
    # Primary order requested by the user: Frontend -> layout -> QA.
    # Within the same role, keep the strongest fit/profit score first.
    return sorted(
        eligible,
        key=lambda x: (x.get("role_priority", 99), -x.get("profit_score", 0)),
    )
