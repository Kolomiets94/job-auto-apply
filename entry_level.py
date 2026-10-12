"""Shared entry-level titles and confirmed internship compensation."""
import re

JUNIOR = re.compile(r"(?<![a-zа-я])(?:junior|jr\.?|джуниор|джун|младший|младшая)(?![a-zа-я])", re.I)
PLACEMENT = re.compile(r"\bintern(?:ship)?\b|\btrainee\b|стаж[её]р|стажиров|практикант|практик[ауы]\b|практике\b", re.I)


def is_placement(title):
    return bool(PLACEMENT.search(str(title or "")))


def is_entry_level(title):
    return bool(JUNIOR.search(str(title or ""))) or is_placement(title)


def placement_is_paid(lead):
    text = " ".join(str(lead.get(k) or "") for k in ("title", "description", "requirements")).lower()
    if re.search(r"\bunpaid\b|\bnon[- ]paid\b|\bwithout (?:pay|compensation)\b|неоплачиваем|без\s+оплаты|оплата\s+не\s+предусмотрена|не\s+оплачива", text):
        return False
    salary = lead.get("salary")
    values = ([salary.get(k) for k in ("from", "to", "amount")] if isinstance(salary, dict) else [])
    values += [lead.get("salary_min"), lead.get("salary_max")]
    if any(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in values):
        return True
    if re.search(r"\bpaid\s+(?:[\w/-]+\s+){0,4}(?:internship|intern|trainee|placement)\b|\b(?:internship|intern|trainee|placement)\s*(?:is|:|-)?\s*paid\b|оплачиваем|стажиров\w*\s+оплачива|практик\w*\s+оплачива|\bстипендия\b|\bstipend\b", text):
        return True
    # Explicit compensation amounts in descriptions or textual salary fields.
    compensation = str(salary or "") + " " + text
    return bool(re.search(r"(?:зарплата|оклад|оплата|salary|compensation|стипендия|stipend)\s*[:—-]?\s*(?:от|from)?\s*[1-9][\d\s.,]*\s*(?:₽|руб|rub|rur|usd|eur|доллар|евро|\$|€)", compensation, re.I))
