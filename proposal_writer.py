"""Personalized, evidence-based cover letters from verified candidate projects."""

import re
from profit_ranker import _role_category

PROJECTS = {
    "travel": ("TravelBlog", "https://github.com/Kolomiets94/travel-blog"),
    "movie": ("VKMarusya", "https://github.com/Kolomiets94/VKMarusya"),
    "audio": ("Audioplayer", "https://github.com/Kolomiets94/audioplayer"),
}


def _is_english(lead, context):
    language = str(lead.get("language") or "").strip().lower()
    if language.startswith("en"):
        return True
    if language.startswith("ru"):
        return False
    title = str(lead.get("title") or "")
    description = str(lead.get("description") or "")
    return not bool(re.search(r"[А-Яа-яЁё]", title + " " + description))


def make_proposal(lead):
    """Match the letter to the vacancy while using only verified personal-project facts."""
    title = str(lead.get("title") or "Junior Frontend Developer").strip()
    context = " ".join(str(lead.get(k) or "") for k in
                       ("title", "description", "requirements")).lower()
    category = _role_category(lead)
    english = _is_english(lead, context)

    if category == "layout":
        name, url = PROJECTS["travel"]
        detail_ru = "адаптивную вёрстку на HTML, CSS и SCSS"
        detail_en = "responsive layouts with HTML, CSS and SCSS"
    elif any(word in context for word in ("redux", "поиск", "search", "избран")):
        name, url = PROJECTS["movie"]
        detail_ru = "поиск с debounce и работу с избранным на Redux Toolkit"
        detail_en = "debounced search and favourites with Redux Toolkit"
    elif any(word in context for word in ("audio", "аудио", "player", "плеер")):
        name, url = PROJECTS["audio"]
        detail_ru = "управление воспроизведением через HTML5 Audio API"
        detail_en = "playback controls using the HTML5 Audio API"
    else:
        name, url = PROJECTS["travel"]
        detail_ru = "авторизацию, защищённые маршруты, CRUD и работу с REST API"
        detail_en = "authentication, protected routes, CRUD and REST API integration"

    if english:
        return (
            f"Hello! I'm applying for {title}. "
            "Since August 2024, I've been developing personal frontend projects with React, "
            "TypeScript, JavaScript, Redux Toolkit and REST APIs. "
            f"In {name}, I implemented {detail_en}: {url}. "
            "My experience is project-based, and I'd be glad to discuss how it matches your team's needs."
        )
    return (
        f"Здравствуйте! Откликаюсь на вакансию «{title}». "
        "С августа 2024 года развиваю личные frontend-проекты на React, TypeScript, JavaScript "
        "и Redux Toolkit, работаю с REST API. "
        f"В проекте {name} реализовал {detail_ru}: {url}. "
        "Мой опыт получен на собственных проектах; буду рад обсудить, чем могу быть полезен вашей команде."
    )
