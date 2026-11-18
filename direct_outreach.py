""""Public-source, draft-only direct outreach research helpers.

The module never guesses a person's identity/email and never sends messages.
It generates targeted public search links and a short draft with explicit
personalization placeholders when no verified evidence is available.
"""
from urllib.parse import quote_plus


ROLE_TARGETS = (
    ("Engineering Manager / Team Lead", "Engineering Manager OR Team Lead OR Tech Lead"),
    ("Head of Engineering", "Head of Engineering OR Engineering Lead"),
    ("CTO / Founder (small companies)", "CTO OR Founder OR Co-Founder"),
    ("Engineer for referral", "Software Engineer OR Developer"),
    ("Recruiter", "Technical Recruiter OR Talent Acquisition"),
)


def _first_text(lead, *keys):
    for key in keys:
        value = lead.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_outreach_draft(lead):
    company = _first_text(lead, "company", "employer", "company_name")
    if not company:
        return None

    title = _first_text(lead, "title") or "Junior Developer"
    domain = _first_text(lead, "company_domain", "domain", "employer_domain")
    vacancy_url = _first_text(lead, "url", "apply_url")
    evidence = _first_text(
        lead, "personalization_evidence", "team_context", "project_context"
    )
    portfolio = _first_text(lead, "portfolio_url", "github_url", "project_url")
    skills = lead.get("matched_skills") or lead.get("resume_skills_match") or []
    skills_text = ", ".join(str(item) for item in skills[:5] if item)
    company_q = quote_plus(f'"{company}" official website team about contact')
    people_links = []
    for label, terms in ROLE_TARGETS:
        q = quote_plus(f'"{company}" ({terms})')
        people_links.append({
            "priority": label,
            "url": f"https://www.linkedin.com/search/results/people/?keywords={q}",
        })
    github_q = quote_plus(f'"{company}"')
    github_url = f"https://github.com/search?q={github_q}&type=users"
    domain_search = (
        f"https://hunter.io/search/{quote_plus(domain)}" if domain else ""
    )

    opening = (
        f"Увидел ваш материал о {evidence}. "
        if evidence else
        f"Увидел вакансию «{title}» в {company}. "
        "Изучаю вашу команду и хочу обратиться по делу. "
    )
    proof = f"Мои релевантные навыки: {skills_text}. " if skills_text else ""
    portfolio_line = f"Мой проект/портфолио: {portfolio}. " if portfolio else (
        "Портфолио: [добавьте ссылку на самый релевантный работающий проект]. "
    )
    note = (
        f"Здравствуйте! {opening}{proof}{portfolio_line}"
        "Могу быть полезен в задачах команды, связанных с этой вакансией. "
        "Подскажите, пожалуйста, актуален ли поиск и будет ли уместно "
        "обсудить это в коротком 15-минутном разговоре?"
    )

    return {
        "company": company,
        "title": title[:100],
        "vacancy_url": vacancy_url,
        "contact_priority": [item["priority"] for item in people_links],
        "people_search_links": people_links,
        # Backwards-compatible alias for earlier consumers/tests.
        "people_search_url": people_links[0]["url"],
        "github_people_search_url": github_url,
        "company_team_search_url": f"https://www.google.com/search?q={company_q}",
        "public_email_lookup_url": domain_search,
        "personalization_evidence": evidence or "[найти конкретный продукт, PR или пост]",
        "portfolio_url": portfolio,
        "message_draft": note,
        "follow_up_after_days": 7,
        "follow_up_limit": 1,
        "sent": False,
        "email_verified": False,
    }


def build_outreach_drafts(leads, limit=5):
    """Build unique company drafts from ranked vacancies; draft-only by design."""
    drafts = []
    seen = set()
    for lead in leads:
        draft = build_outreach_draft(lead)
        if not draft:
            continue
        key = draft["company"].casefold()
        if key in seen:
            continue
        seen.add(key)
        drafts.append(draft)
        if len(drafts) >= limit:
            break
    return drafts
