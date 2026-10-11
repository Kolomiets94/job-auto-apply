"""Short, evidence-based cover letters for the candidate's verified projects."""

from profit_ranker import _role_category

PROJECTS = {
    "travel": ("TravelBlog", "https://github.com/Kolomiets94/travel-blog"),
    "movie": ("VKMarusya", "https://github.com/Kolomiets94/VKMarusya"),
    "audio": ("Audioplayer", "https://github.com/Kolomiets94/audioplayer"),
}


def make_proposal(lead):
    """Draft from known portfolio facts; never infer commercial experience."""
    title = str(lead.get("title") or "позиция Junior").strip()
    context = " ".join(str(lead.get(k) or "") for k in
                       ("title", "description", "requirements")).lower()
    category = _role_category(lead)
    english = lead.get("language") == "en"

    if category == "qa":
        name, url = PROJECTS["travel"]
        if english:
            return (f"Hello! I'm applying for {title}. "
                    "I have manually tested my own React web applications, including form validation, navigation, and API error handling. "
                    f"One project is {name}: {url}. "
                    "I would be glad to discuss my testing approach and learn your QA process.")
        return (f"Здравствуйте! Откликаюсь на вакансию «{title}». "
                "Проводил ручное тестирование собственных веб-приложений на React: проверял формы, навигацию и обработку ошибок API. "
                f"Пример проекта — {name}: {url}. "
                "Готов рассказать о проверках и освоить процессы тестирования вашей команды.")

    if category == "layout":
        name, url = PROJECTS["travel"]
        detail_ru = "адаптивный интерфейс на SCSS" if "адаптив" in context or "responsive" in context else "интерфейс на SCSS"
        detail_en = "a responsive SCSS interface" if "responsive" in context else "an SCSS interface"
    elif "redux" in context or "поиск" in context or "search" in context:
        name, url = PROJECTS["movie"]
        detail_ru = "поиск с задержкой ввода и избранное на Redux Toolkit"
        detail_en = "debounced search and favorites with Redux Toolkit"
    elif "audio" in context or "аудио" in context:
        name, url = PROJECTS["audio"]
        detail_ru = "управление воспроизведением через HTML5 Audio API"
        detail_en = "playback controls using the HTML5 Audio API"
    else:
        name, url = PROJECTS["travel"]
        detail_ru = "маршруты с защитой доступа и взаимодействие с REST API"
        detail_en = "protected routes and REST API interaction"

    if english:
        return (f"Hello! I'm applying for {title}. "
                "I have practiced frontend development in personal projects. "
                f"In {name}, I implemented {detail_en}: {url}. "
                "I would be glad to discuss how this example relates to your task.")
    return (f"Здравствуйте! Откликаюсь на вакансию «{title}». "
            "Практиковался в разработке интерфейсов на личных проектах. "
            f"В проекте {name} реализовал {detail_ru}: {url}. "
            "Готов обсудить, как этот пример соотносится с вашей задачей.")
