"""Privacy-safe publication freshness diagnostics for vacancy batches."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def _published_at(value):
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
            except (TypeError, ValueError, OverflowError):
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_freshness_report(leads, now=None):
    """Count publication age without guessing when source timestamps are absent."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    buckets = {
        "до 3 дней": 0,
        "4–7 дней": 0,
        "8–30 дней": 0,
        "старше 30 дней": 0,
        "дата неизвестна": 0,
    }
    for lead in leads or []:
        published = _published_at(lead.get("published"))
        if published is None:
            buckets["дата неизвестна"] += 1
            continue
        age_days = (now - published).total_seconds() / 86400
        if age_days < 0:
            buckets["дата неизвестна"] += 1
        elif age_days <= 3:
            buckets["до 3 дней"] += 1
        elif age_days <= 7:
            buckets["4–7 дней"] += 1
        elif age_days <= 30:
            buckets["8–30 дней"] += 1
        else:
            buckets["старше 30 дней"] += 1

    total = sum(buckets.values())
    lines = ["СВЕЖЕСТЬ ВАКАНСИЙ (по дате источника):", f"Проверено: {total}"]
    lines.extend(f"- {label}: {count}" for label, count in buckets.items())
    lines.append("Неизвестная дата не считается свежей; возраст не меняет фильтры допуска.")
    return "\n".join(lines)
