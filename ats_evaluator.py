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

def build_market_report(leads):
    """Summarize recurring resume-to-vacancy gaps across one discovery batch."""
    from collections import Counter

    items = [lead for lead in leads if lead.get("ats_method") == "transparent_heuristic_v1"]
    total = len(items)
    if not total:
        return (
            "ATS-АНАЛИЗ РЫНКА\n"
            "В этой выборке нет вакансий с рассчитанным ATS-анализом. "
            "Проверь наличие текста резюме и описаний вакансий."
        )

    missing_skills = Counter()
    for lead in items:
        missing_skills.update(set(lead.get("ats_missing_keywords") or []))

    buckets = [
        {
            "title": "Не хватает технологий или навыков",
            "count": sum(bool(lead.get("ats_missing_keywords")) for lead in items),
            "detail": (
                "Чаще всего не совпали: " +
                ", ".join(f"{name} ({count})" for name, count in missing_skills.most_common(6))
                if missing_skills else "Список недостающих навыков не выявлен."
            ),
            "action": (
                "Добавляй технологию в резюме только если действительно применял её. "
                "Если опыта нет — выбери 1–2 часто встречающихся навыка, изучи их и закрепи небольшим проектом."
            ),
        },
        {
            "title": "Требуется больший стаж",
            "count": sum(bool(lead.get("ats_experience_gap")) for lead in items),
            "detail": "В описаниях этих вакансий явно указан стаж от 1 года и выше.",
            "action": (
                "Не приписывай себе коммерческий стаж. Усиль раздел проектов: даты, личная роль, "
                "задачи, сложность, стек, ссылки на код и работающий результат. Такие вакансии "
                "не исключай автоматически — проектный опыт можно предложить на рассмотрение."
            ),
        },
        {
            "title": "Работодатель просит коммерческий опыт",
            "count": sum(bool(lead.get("ats_commercial_gap")) for lead in items),
            "detail": "В тексте вакансии найдено прямое упоминание коммерческого опыта, которого резюме не заявляет.",
            "action": (
                "Опиши только реальные учебные и личные проекты: задачу, свою роль, стек и реализованные функции. "
                "Не называй проектную практику коммерческой работой; можно откликаться, если требование не выглядит безусловным."
            ),
        },
        {
            "title": "Недостаточно подтверждений проектной практики",
            "count": sum(not bool(lead.get("ats_project_evidence")) for lead in items),
            "detail": "В тексте резюме не обнаружены ожидаемые маркеры проектной практики.",
            "action": (
                "Подробно опиши реальные проекты: авторизацию и защищённые маршруты, CRUD, REST API, "
                "debounce-поиск, валидацию и обработку ошибок. Добавь GitHub-ссылки, если они доступны."
            ),
        },
        {
            "title": "Низкое текстовое совпадение с профилем вакансии",
            "count": sum((lead.get("ats_score") or 0) < 60 for lead in items),
            "detail": "У этих вакансий эвристическая оценка ATS ниже 60 из 100.",
            "action": (
                "Проверь, действительно ли это Frontend/React/JavaScript/TypeScript и Junior/Intern роль. "
                "Если да — адаптируй порядок и формулировки подтверждённых навыков под описание вакансии; "
                "если стек другой — не подгоняй резюме искусственно."
            ),
        },
    ]
    buckets.sort(key=lambda item: item["count"], reverse=True)

    lines = [
        "МАССОВЫЙ ATS-ОТЧЁТ",
        f"Вакансий проанализировано: {total}",
        "Причины могут пересекаться: одна вакансия может учитываться в нескольких категориях.",
        "",
        "5 ОСНОВНЫХ ПРИЧИН И ЧТО ДЕЛАТЬ:",
    ]
    for number, item in enumerate(buckets[:5], 1):
        share = item["count"] * 100.0 / total
        lines.extend([
            f"{number}. {item['title']} — {item['count']} вакансий ({share:.1f}%).",
            f"   Детали: {item['detail']}",
            f"   Что сделать: {item['action']}",
        ])
    avg_score = round(sum((lead.get("ats_score") or 0) for lead in items) / total)
    strong = sum(lead.get("ats_verdict") == "strong_match" for lead in items)
    review = sum(lead.get("ats_verdict") == "review" for lead in items)
    weak = sum(lead.get("ats_verdict") == "weak_match" for lead in items)
    lines.extend([
        "",
        f"Средняя эвристическая ATS-оценка: {avg_score}/100.",
        f"Распределение: сильное совпадение — {strong}, проверить вручную — {review}, слабое совпадение — {weak}.",
        "Важно: это анализ текста вакансий и резюме, а не доступ к закрытым ATS работодателей и не гарантия отказа.",
    ])
    top_gaps = [name for name, _count in missing_skills.most_common(3)]
    lines.extend([
        "",
        "ПЛАН ДЕЙСТВИЙ:",
        "Можно исправить сразу: переставь подтверждённые навыки ближе к началу резюме; " +
        "раскрой реальные проекты (задача, твоя роль, стек, реализованные функции и результат); " +
        "добавь ссылки на GitHub и демо, если они доступны. Не добавляй навыки, которыми не владеешь.",
        "Нужно подтвердить проектом: для навыков, которые уже применял, укажи конкретный проект и свою реализацию. " +
        "Если практики пока нет, создай небольшой законченный проект и приложи код.",
        ("Нужно освоить дополнительно: чаще всего в выборке не совпали " + ", ".join(top_gaps) +
         ". Сначала проверь, что эти навыки действительно относятся к целевым Junior Frontend вакансиям; " +
         "изучай приоритетные, но не вписывай их в резюме до практического применения.")
        if top_gaps else
        "Нужно освоить дополнительно: в этой выборке устойчивого повторяющегося пробела по технологиям не выявлено; " +
        "не добавляй новые технологии без необходимости.",
    ])
    return "\n".join(lines)


def build_manual_review_report(leads, limit=15):
    """List borderline and strong-ATS employment vacancies rejected by the internal ranker."""
    from profit_ranker import rank_lead

    candidates = []
    for lead in list(leads or []):
        url = str(lead.get("url") or "").strip()
        if not url:
            continue
        decision = rank_lead(lead)
        if decision.get("eligible"):
            continue
        manual_review = bool(decision.get("manual_review_required"))
        strong_ats = lead.get("ats_verdict") == "strong_match"
        if not (manual_review or strong_ats):
            continue
        score = lead.get("ats_score")
        reason = (
            decision.get("manual_review_reason")
            if manual_review else decision.get("rank_reason")
        ) or decision.get("rank_reason") or "Причина не указана"
        candidates.append({
            "title": str(lead.get("title") or "Вакансия")[:100],
            "source": str(lead.get("source") or "unknown")[:40],
            "url": url,
            "score": score if isinstance(score, (int, float)) else -1,
            "manual_review": manual_review,
            "reason": str(reason)[:180],
        })

    candidates.sort(key=lambda item: (item["score"], item["manual_review"]), reverse=True)
    manual_count = sum(item["manual_review"] for item in candidates)
    strong_count = sum(item["score"] >= 80 for item in candidates)
    lines = [
        "РУЧНАЯ ПРОВЕРКА: ПОГРАНИЧНЫЕ И СИЛЬНЫЕ ATS-ВАКАНСИИ",
        f"Найдено кандидатов для просмотра: {len(candidates)} "
        f"(пограничных: {manual_count}; ATS 80+: {strong_count}).",
        "Все вакансии в списке остаются исключёнными из автоматических откликов.",
    ]
    if not candidates:
        lines.append("В этой выборке таких вакансий нет.")
        return "\n".join(lines)

    shown = candidates[:max(0, int(limit))]
    for number, item in enumerate(shown, 1):
        score_label = f"{item['score']}/100" if item["score"] >= 0 else "н/д"
        kind = "ручная проверка" if item["manual_review"] else "сильный ATS, отказ ранкера"
        lines.extend([
            f"{number}. {item['title']} [{item['source']}] — ATS {score_label}; {kind}.",
            f"   Причина: {item['reason']}",
            f"   {item['url']}",
        ])
    if len(candidates) > len(shown):
        lines.append(f"Показаны первые {len(shown)} из {len(candidates)}.")
    return "\n".join(lines)


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
    required_lines = [line.strip() for line in re.split(r"[\n;]|(?<=[.!?])\s+", description)
                     if required_pattern.search(line)]
    required_missing = [
        skill for skill in missing
        if any(_contains(line.lower(), SKILL_ALIASES.get(skill, (skill,))) for line in required_lines)
    ]
    hard_gaps = []
    if required_missing:
        hard_gaps.append("Не совпали явно обязательные навыки: " + ", ".join(required_missing) + ".")
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
        "ats_required_missing_keywords": required_missing[:20],
        "ats_risk_flags": hard_gaps[:8],
        "ats_recruiter_note": recruiter_note,
        "ats_role_match": role_match,
        "ats_junior_match": junior_match,
        "ats_project_evidence": project_evidence,
        "ats_experience_gap": any("опыте вакансии указано" in flag.lower() or "указан опыт от" in flag.lower() for flag in hard_gaps),
        "ats_commercial_gap": any("коммерческий опыт" in flag.lower() for flag in hard_gaps),
        "ats_method": "transparent_heuristic_v1",
    }


def build_filter_report(leads):
    """Report Job Auto Apply's own primary exclusion reasons separately from ATS."""
    from collections import Counter
    from profit_ranker import rank_lead

    items = list(leads or [])
    if not items:
        return (
            "ФИЛЬТРЫ JOB AUTO APPLY\n"
            "Нет вакансий для анализа фильтров в этой выборке."
        )

    reasons = Counter()
    passed = 0
    for lead in items:
        decision = rank_lead(lead)
        if decision.get("eligible"):
            passed += 1
        else:
            reasons[str(decision.get("rank_reason") or "unknown")] += 1

    labels = {
        "internship/trainee excluded": "Стажировка/trainee исключена текущими правилами",
        "non-target QA role": "QA не входит в основной целевой профиль",
        "excluded job title": "Исключённый уровень или тип должности",
        "office/on-site roles are excluded": "Офисный формат",
        "office work is excluded; fully remote only": "Офисный формат",
        "hybrid work is excluded; fully remote only": "Гибридный формат",
        "remote work format is not confirmed": "Удалённый формат не подтверждён",
        "hybrid is allowed only in Yekaterinburg": "Гибрид не в Екатеринбурге",
        "hybrid work is allowed only in Yekaterinburg": "Гибрид не в Екатеринбурге",
        "remote work format is not confirmed": "Удалённый формат не подтверждён",
        "mandatory nonlocal relocation": "Обязательный переезд в другой город",
        "mandatory unsupported stack": "Обязательный неподдерживаемый стек",
        "SQL outside confirmed stack": "SQL вне подтверждённого стека",
        "known stale vacancy (2023)": "Устаревшая вакансия",
        "salary below configured floor": "Зарплата ниже внутреннего порога",
        "salary outside configured range": "Зарплата вне допустимого диапазона",
        "explicit location/work-authorization restriction": "География или право на работу не подходят",
        "non-target job title": "Нецелевая должность",
        "job title outside target roles": "Название вне целевых Frontend/React ролей",
        "experience from 3 years": "Требуется от 3 лет опыта",
        "experience range above 3 years": "Вилка опыта выше 3 лет",
        "three years required": "Требуется 3 года опыта",
        "experience above 3 years": "Требуется более 3 лет опыта",
        "layout entry level not confirmed": "Для вёрстки не подтверждён начальный уровень",
        "not Junior or 0-3 years": "Не подтверждён Junior / диапазон 0–3 года",
        "freelance title outside demonstrated stack": "Фриланс-задача вне подтверждённого стека",
        "freelance title requires unsupported technology": "Фриланс требует неподдерживаемую технологию",
        "freelance project too complex/out of scope": "Фриланс-задача слишком сложная или вне профиля",
    }
    lines = [
        "ФИЛЬТРЫ JOB AUTO APPLY — ОТДЕЛЬНЫЙ АНАЛИЗ",
        f"Вакансий проверено внутренним ранкером: {len(items)}",
        f"Прошли внутренние фильтры: {passed}; исключены: {len(items) - passed}.",
        "Ниже указана первая сработавшая причина по порядку правил rank_lead; "
        "это не полный список всех возможных проблем одной вакансии.",
        "Причины этого раздела не смешиваются с ATS-пробелами; одна вакансия может "
        "одновременно пройти внутренние фильтры и иметь ATS-пробелы, или наоборот.",
        "",
        "ОСНОВНЫЕ ПРИЧИНЫ ИСКЛЮЧЕНИЯ:",
    ]
    if not reasons:
        lines.append("В этой выборке внутренние фильтры не исключили ни одной вакансии.")
    else:
        for number, (reason, count) in enumerate(reasons.most_common(8), 1):
            label = labels.get(reason, reason)
            lines.append(f"{number}. {label} — {count} вакансий ({count * 100.0 / len(items):.1f}%).")
    lines.extend([
        "",
        "Как трактовать результат:",
        "- Зарплата ниже порога — можно пересмотреть только если пользователь изменит нижнюю границу.",
        "- Офис/неподходящий гибрид/география — не исправляется формулировкой резюме.",
        "- Недостаточный Junior-сигнал или неподдерживаемый обязательный стек — проверять описание вручную; "
        "не приписывать коммерческий опыт или отсутствующие технологии.",
        "- Внутренний ранкер показывает первую причину отказа, а не окончательный вердикт работодателя.",
    ])
    return "\n".join(lines)
