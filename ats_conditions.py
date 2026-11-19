"""Conservative checks for job conditions that keyword matching cannot prove.

Each dimension is tri-state: confirmed, blocked, or unknown. Missing evidence is
never silently treated as permission to apply.
"""
import re


REMOTE_RE = re.compile(
    r"\b(?:fully remote|100% remote|remote[- ]only|work from anywhere|"
    r"полностью удал[её]нн\w*|только удал[её]нн\w*)\b", re.I
)
HYBRID_RE = re.compile(r"\b(?:hybrid|гибрид\w*)\b", re.I)
OFFICE_RE = re.compile(
    r"\b(?:on[- ]?site|in[- ]office|office[- ]based|офисн\w+ формат|работа в офисе)\b", re.I
)
RUSSIA_ALLOW_RE = re.compile(
    r"(?:candidates?|applicants?|employees?|residents?|based)\s+(?:from|in)\s+russia|"
    r"росси\w*\s+(?:разрешен|доступен|принима|рассматрива)|"
    r"(?:кандидат|соискател|сотрудник)\w*\s+из\s+росси\w*", re.I
)
RUSSIA_BLOCK_RE = re.compile(
    r"(?:not|cannot|can't|unable to)\s+(?:hire|employ|accept)\s+.*russia|"
    r"(?:excluding|except)\s+russia|"
    r"не\s+(?:нанима|рассматрива|принима)\w*\s+.*росси\w*", re.I
)
PAID_RE = re.compile(
    r"\b(?:paid|salary|stipend|compensated|remuneration)\b|"
    r"оплачиваем\w*|зарплат\w*|стипенди\w*", re.I
)
UNPAID_RE = re.compile(r"\b(?:unpaid|volunteer)\b|неоплачиваем\w*", re.I)


def _joined(lead):
    parts = [
        lead.get("title"), lead.get("description"), lead.get("requirements"),
        lead.get("work_mode"), lead.get("location"), lead.get("employment"),
        lead.get("opportunity_type"), lead.get("salary"),
    ]
    return " ".join(str(part or "") for part in parts)


def assess_job_conditions(lead):
    """Return explicit remote, Russia-eligibility and paid-placement assessments."""
    text = _joined(lead)
    mode = str(lead.get("work_mode") or "").lower()

    if "remote" in mode or "удален" in mode or REMOTE_RE.search(text):
        remote = "confirmed"
    elif "hybrid" in mode or "гибрид" in mode or HYBRID_RE.search(text):
        remote = "blocked"
    elif "office" in mode or "onsite" in mode or "офис" in mode or OFFICE_RE.search(text):
        remote = "blocked"
    else:
        remote = "unknown"

    if RUSSIA_BLOCK_RE.search(text):
        russia = "blocked"
    elif RUSSIA_ALLOW_RE.search(text):
        russia = "confirmed"
    else:
        russia = "unknown"

    placement = str(lead.get("opportunity_type") or "").lower() in {
        "paid_placement", "internship", "intern", "trainee", "practice", "стажировка", "практика"
    }
    salary = lead.get("salary")
    salary_known = bool(salary) or bool(re.search(r"\d[\d\s.,]*\s*(?:₽|руб\.?|rub|eur|usd|€|\$)", text, re.I))
    if UNPAID_RE.search(text):
        payment = "blocked"
    elif PAID_RE.search(text) or salary_known:
        payment = "confirmed"
    else:
        payment = "unknown"

    return {
        "ats_remote_status": remote,
        "ats_russia_eligibility": russia,
        "ats_paid_status": payment if placement else "not_applicable",
        "ats_conditions_method": "explicit_evidence_tri_state_v1",
    }
