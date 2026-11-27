"""Short, evidence-based cover letters using only verified portfolio references."""

from profit_ranker import _role_category

PROJECTS = {
    "travel": ("TravelBlog", "https://github.com/Kolomiets94/travel-blog"),
    "movie": ("VKMarusya", "https://github.com/Kolomiets94/VKMarusya"),
    "audio": ("Audioplayer", "https://github.com/Kolomiets94/audioplayer"),
}


def make_proposal(lead):
    """Draft a concise letter without deriving candidate skills from vacancy text."""
    title = str(lead.get("title") or "позиция Junior").strip()
    category = _role_category(lead)
    language = str(lead.get("language") or "").lower()

    # Project selection depends only on the role/title, never on description or
    # requirements. The draft intentionally avoids feature/skill claims: a
    # vacancy mentioning a technology is not evidence that the candidate used it.
    if category in ("qa", "layout"):
        name, url = PROJECTS["travel"]
    elif "react" in title.lower() or "frontend" in title.lower():
        name, url = PROJECTS["movie"]
    else:
        name, url = PROJECTS["travel"]

    if language == "en":
        return (
            f"Hello! I'm applying for {title}. "
            "I have practiced development through personal projects. "
            f"One example is {name}: {url}. "
            "I would be glad to walk you through the code and discuss how I could contribute."
        )

    return (
        f"Здравствуйте! Откликаюсь на вакансию «{title}». "
        "Практиковался в разработке на личных проектах. "
        f"Один из примеров — {name}: {url}. "
        "Готов показать код и обсудить, чем могу быть полезен вашей команде."
    )
