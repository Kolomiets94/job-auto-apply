"""Draft-only direct outreach helpers for shortlisted job leads.

Never guesses a person's identity or sends messages. It creates search links
and a customizable note so the candidate can contact a real decision-maker.
"""
from urllib.parse import quote_plus


def build_outreach_draft(lead):
    company = str(
        lead.get("company") or lead.get("employer") or lead.get("company_name") or ""
    ).strip()
    title = str(lead.get("title") or "разработчика").strip()
    skills = lead.get("matched_skills") or lead.get("resume_skills_match") or []
    skills_text = ", ".join(str(item) for item in skills[:5] if item)
    if not company:
        return None

    query = quote_plus(f'"{company}" CTO OR технический директор OR team lead')
    company_query = quote_plus(f'"{company}" официальный сайт контакты')
    role = title[:100]
    note = (
        f"Здравствуйте! Увидел вакансию «{role}» в компании {company}. "
        "Мне интересна ваша команда и продукт. Я Junior Frontend Developer, "
        "работаю с React, TypeScript и JavaScript. "
        + (f"В моих проектах использую: {skills_text}. " if skills_text else "")
        + "Могу прислать резюме и GitHub-портфолио. "
        "Подскажите, пожалуйста, кому лучше адресовать отклик?"
    )
    return {
        "company": company,
        "title": role,
        "vacancy_url": str(lead.get("url") or ""),
        "people_search_url": f"https://www.linkedin.com/search/results/people/?keywords={query}",
        "company_search_url": f"https://www.google.com/search?q={company_query}",
        "message_draft": note,
        "sent": False,
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
