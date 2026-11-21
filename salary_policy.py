"""Conservative monthly salary policy for employment vacancies."""
import re

REGULAR_MIN_RUB = 50_000
PLACEMENT_MIN_RUB = 0
REGULAR_MAX_RUB = 70_000
PLACEMENT_MAX_RUB = 50_000
_UNPAID = re.compile(r"\bunpaid\b|\bnon[- ]paid\b|\bwithout (?:pay|compensation)\b|неоплачиваем\w*|без\s+оплаты|оплата\s+не\s+предусмотрена|не\s+оплачива", re.I)
_AMOUNT = re.compile(r"(?P<amount>\d[\d\s\u00a0]*(?:[.,]\d+)?)\s*(?P<currency>₽|руб(?:лей|ля|ль)?\.?|RUB|RUR|USD|\$|EUR|€)", re.I)


def _monthly_factor(period):
    period = str(period or "").strip().lower()
    if not period or period in ("month", "monthly", "месяц", "мес", "мес."): return 1.0
    if period in ("year", "yearly", "annual", "annually", "год", "годовой", "в год"): return 1.0 / 12.0
    if period in ("week", "weekly", "неделя", "недельно", "в неделю"): return 52.0 / 12.0
    if period in ("day", "daily", "день", "дневной", "в день"): return 22.0
    if period in ("hour", "hourly", "час", "почасовая", "в час"): return 176.0
    return None


def _period_from_text(text):
    text = str(text or "").lower()
    if re.search(r"\b(?:per\s+)?(?:year|yearly|annual(?:ly)?)\b|в\s+год|годов\w*|годовая", text): return "year"
    if re.search(r"\b(?:per\s+)?week(?:ly)?\b|в\s+недел\w*|недельно", text): return "week"
    if re.search(r"\b(?:per\s+)?day\b|в\s+день|ежедневно", text): return "day"
    if re.search(r"\b(?:per\s+)?hour(?:ly)?\b|в\s+час|почасов\w*", text): return "hour"
    if re.search(r"\b(?:per\s+)?month(?:ly)?\b|в\s+месяц|за\s+месяц|ежемесячно", text): return "month"
    return None


def _number(value, allow_zero=False):
    if isinstance(value, bool): return None
    if isinstance(value, (int, float)) and (value > 0 or (allow_zero and value == 0)): return float(value)
    return None


def salary_decision(lead):
    """Return eligible, rejected, or manual_review for a job's salary."""
    title = str(lead.get("title") or lead.get("name") or "")
    placement = bool(re.search(r"\bintern(?:ship)?\b|\btrainee\b|стаж[её]р|стажиров|практикант|практик", title, re.I))
    if str(lead.get("source") or "").lower() in {
        "fl_ru", "habr_freelance", "freelancehunt", "peopleperhour",
        "prolinker", "prolinker_firecrawl", "upwork_frontend", "weblancer", "freelancer_com",
    }: return "eligible"

    text = " ".join(str(lead.get(k) or "") for k in ("title", "description", "requirements", "snippet"))
    salary = lead.get("salary")
    salary_text = str(salary or "")
    combined = text + " " + salary_text
    floor = PLACEMENT_MIN_RUB if placement else REGULAR_MIN_RUB
    ceiling = PLACEMENT_MAX_RUB if placement else REGULAR_MAX_RUB
    if placement and not salary:
        return "eligible"
    currency, period, low, high = "", None, None, None
    if isinstance(salary, dict):
        currency = str(salary.get("currency") or "").upper()
        period = salary.get("period")
        low, high = _number(salary.get("from"), allow_zero=placement), _number(salary.get("to"), allow_zero=placement)
        amount = _number(salary.get("amount"), allow_zero=placement)
        if low is None and high is None and amount is not None: low = high = amount
        if not period and currency in ("RUR", "RUB"): period = "month"
    else:
        match = _AMOUNT.search(salary_text) or _AMOUNT.search(combined)
        if match:
            raw = match.group("amount").replace("\u00a0", "").replace(" ", "").replace(",", ".")
            try: amount = float(raw)
            except ValueError: amount = None
            currency = match.group("currency").upper()
            if currency == "₽" or currency.startswith("РУБ"): currency = "RUB"
            if currency == "$": currency = "USD"
            if currency == "€": currency = "EUR"
            low = high = amount
            period = _period_from_text(combined)

    if low is None and high is None: return "eligible" if placement else "manual_review"
    if currency not in ("RUR", "RUB"): return "manual_review"
    factor = _monthly_factor(period)
    if factor is None or low is None: return "manual_review"
    monthly_low = low * factor
    monthly_high = (high if high is not None else low) * factor
    if monthly_low > monthly_high: monthly_low, monthly_high = monthly_high, monthly_low
    if monthly_high < floor or monthly_low > ceiling: return "rejected"
    if monthly_low < floor or monthly_high > ceiling: return "manual_review"
    return "eligible"
