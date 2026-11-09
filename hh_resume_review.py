"""Deterministic, evidence-grounded review helpers for HH resume text."""
import re

SKILL_TERMS = (
    "Python", "JavaScript", "TypeScript", "React", "Redux", "HTML", "CSS",
    "SCSS", "REST API", "SQL", "PostgreSQL", "Git", "Docker", "Playwright",
    "Selenium", "Pytest", "Figma", "Vite", "Webpack", "Node.js",
    "тестирование", "автоматизация", "ручное тестирование",
)
SECTION_HINTS = {
    "summary": ("о себе", "обо мне", "профессиональные навыки"),
    "experience": ("опыт работы", "опыт проектов", "проекты"),
    "education": ("образование", "курсы", "обучение"),
    "skills": ("ключевые навыки", "навыки", "технологии"),
}


def _unique_terms(text, terms):
    lowered = (text or "").casefold()
    return [term for term in terms if term.casefold() in lowered]


def review_resume_text(full_text, vacancy=None):
    text = re.sub(r"\s+", " ", full_text or "").strip()[:50000]
    sections = {key: any(hint in text.casefold() for hint in hints)
                for key, hints in SECTION_HINTS.items()}
    skills = _unique_terms(text, SKILL_TERMS)
    recommendations = []
    if not sections["summary"]:
        recommendations.append("Добавить краткий блок «О себе» с целевой ролью и специализацией.")
    if not sections["experience"]:
        recommendations.append("Проверить, что опыт и учебные/пет-проекты описаны отдельными пунктами с личным вкладом.")
    if not sections["education"]:
        recommendations.append("Проверить наличие образования, курсов или явно обозначенного статуса обучения.")
    if not sections["skills"] or not skills:
        recommendations.append("Добавить отдельный список навыков и технологий, которыми действительно владеете.")
    if len(text) < 500:
        recommendations.append("Извлечённый текст короткий: проверьте полноту страницы резюме вручную.")
    result = {"full_text": text, "text_characters": len(text),
              "detected_sections": sections, "detected_skills": skills,
              "recommendations": recommendations}
    vacancy = vacancy or {}
    if vacancy.get("status") == "read":
        vacancy_text = vacancy.get("title", "") + " " + vacancy.get("description", "")
        required = _unique_terms(vacancy_text, SKILL_TERMS)
        matched = [term for term in required if term.casefold() in text.casefold()]
        missing = [term for term in required if term not in matched]
        result["vacancy_match"] = {
            "vacancy_title": vacancy.get("title", ""),
            "matched_terms": matched, "terms_to_verify": missing,
            "disclaimer": "Совпадение слов не означает подтверждённую компетенцию. Добавляйте только навыки, которыми действительно владеете.",
        }
        title = vacancy.get("title") or "вашу вакансию"
        evidence = ", ".join(skills[:8]) if skills else "навыки, указанные в резюме"
        result["cover_letter_draft"] = (
            f"Здравствуйте!\n\nХочу откликнуться на позицию «{title}». "
            f"В моём резюме указаны следующие навыки и технологии: {evidence}. "
            "Буду рад подробнее рассказать о своём опыте и обсудить, чем могу быть полезен команде.\n\nС уважением"
        )
    return result
