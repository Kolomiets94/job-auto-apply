"""Transparent ATS-style resume screening for frontend vacancies.

This is an explainable local heuristic, not a connection to an employer's private ATS
and not a prediction of any vendor's proprietary score.
"""
import re

SKILL_ALIASES = {
    "react": ("react", "react.js", "reactjs"),
    "typescript": ("typescript", "ts"),
    "javascript": ("javascript", "javascript es6", "js"),
    "redux toolkit": ("redux toolkit", "rtk"),
    "redux": ("redux",),
    "react router": ("react router",),
    "rest api": ("rest api", "restful api", "api integration"),
    "html": ("html", "html5"),
    "css": ("css", "css3"),
    "scss": ("scss", "sass"),
    "git": ("git", "github"),
    "vite": ("vite",),
    "webpack": ("webpack",),
    "figma": ("figma",),
    "responsive layout": ("responsive", "адаптив"),
    "testing": ("testing", "тестирование", "unit test", "jest", "vitest"),
    "sql": ("sql", "postgresql", "mysql"),
    "node.js": ("node.js", "nodejs"),
    "vue": ("vue", "vue.js"),
    "angular": ("angular",),
}

ROLE_TERMS = ("frontend", "front-end", "front end", "react", "фронтенд", "фронтэнд", "веб-разработчик")
JUNIOR_TERMS = ("junior", "entry-level", "entry level", "intern", "trainee", "без опыта", "начинающ")


def _text(value):
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    return str(value or "")


def _contains(text, aliases):
    return any(re.search(r"(?<![a-z0-9+#])" + re.escape(alias) + r"(?![a-z0-9+#])", text, re.I)
               for alias in aliases)


def review_lead(lead, resume_text):
    """Attach explainable ATS-style fields without rejecting a vacancy."""
    resume = _text(resume_text).lower()
    title = _text(lead.get("title") or lead.get("name")).lower()
    description = _text(lead.get("description") or lead.get("requirements")).lower()
    vacancy = " ".join((title, description, _text(lead.get("key_skills")))).lower()

    advertised = []
    for skill, aliases in SKILL_ALIASES.items():
        if _contains(vacancy, aliases):
            advertised.append(skill)
    explicit = [_text(x).strip().lower() for x in (lead.get("key_skills") or []) if _text(x).strip()]
    for item in explicit:
        if item not in advertised:
            advertised.append(item)

    matched = [skill for skill in advertised
               if _contains(resume, SKILL_ALIASES.get(skill, (skill,)))]
    missing = [skill for skill in advertised if skill not in matched]

    # Required wording is reported separately; keyword absence alone is not treated as proof.
    required_pattern = re.compile(
        r"(?:обязательно|required|must have|mandatory|требуется|необходим[оа]?|"
        r"обязательн[аоы]?)",
        re.I,
    )
    required_lines = [line.strip() for line in re.split(r"[\n.;]", description)
                     if required_pattern.search(line)]
    hard_gaps = []
    exp_text = _text(lead.get("experience")).lower()
    if re.search(r"(?:от|from|at least|minimum|min\.?)\s*[2-9]\s*(?:год|года|лет|years?)", exp_text):
        hard_gaps.append("В опыте вакансии указано от 2 лет; проектный опыт не равен коммерческому.")
    elif re.search(r"(?:от|from|at least|minimum|min\.?)\s*1\s*(?:год|года|year)", exp_text):
        hard_gaps.append("Указан опыт от 1 года; стоит уточнить, рассматривают ли проектный опыт.")
    if re.search(r"\b(?:commercial|коммерческ)\w*\b", description) and not re.search(r"\b(?:commercial|коммерческ)\w*\b", resume):
        hard_gaps.append("Работодатель упоминает коммерческий опыт, а в резюме подтверждён проектный.")

    role_match = any(term in title for term in ROLE_TERMS)
    junior_match = any(term in (title + " " + exp_text + " " + description[:1200]) for term in JUNIOR_TERMS)
    project_evidence = any(term in resume for term in ("project", "проект", "crud", "api", "авторизац"))
    coverage = (len(matched) / len(advertised)) if advertised else None

    components = []
    if coverage is not None:
        components.append((60, coverage))
    else:
        components.append((60, 0.5))
    components.append((15, 1.0 if role_match else 0.0))
    components.append((10, 1.0 if junior_match else 0.5))
    components.append((10, 1.0 if project_evidence else 0.0))
    # English is scored only if the vacancy explicitly asks for it.
    if re.search(r"\benglish\b|английск", description):
        english_ok = bool(re.search(r"\bb1\b|\bb2\b|\bc1\b|\bfluent\b|\bintermediate\b|английский", resume))
        components.append((5, 1.0 if english_ok else 0.0))
    else:
        components.append((5, 1.0))
    score = round(sum(weight * ratio for weight, ratio in components))

    if score >= 80 and not hard_gaps:
        verdict = "strong_match"
        recruiter_note = "Резюме выглядит релевантным; есть смысл внимательно изучить проекты."
    elif score >= 60:
        verdict = "review"
        recruiter_note = "Есть совпадение по профилю, но рекрутеру стоит проверить отмеченные пробелы."
    else:
        verdict = "weak_match"
        recruiter_note = "По опубликованным данным совпадение ограниченное."

    return {
        **lead,
        "ats_score": score,
        "ats_verdict": verdict,
        "ats_matched_keywords": matched[:20],
        "ats_missing_keywords": missing[:20],
        "ats_required_lines": required_lines[:8],
        "ats_risk_flags": hard_gaps[:8],
        "ats_recruiter_note": recruiter_note,
        "ats_method": "transparent_heuristic_v1",
    }
