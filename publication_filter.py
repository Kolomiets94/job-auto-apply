"""Fail-closed publication-date filter for job applications."""
import os
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime


def is_new_publication(lead):
    cutoff = os.getenv("MIN_PUBLICATION_DATE", "").strip()
    if not cutoff:
        return True
    try:
        threshold = date.fromisoformat(cutoff)
    except ValueError:
        raise ValueError("MIN_PUBLICATION_DATE must be YYYY-MM-DD")
    raw = lead.get("published") or lead.get("published_at") or lead.get("publication_date")
    if raw is None or str(raw).strip() == "":
        return False
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
        try:
            number = float(raw)
            if number > 1e11:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc).date() >= threshold
        except (ValueError, OverflowError, OSError):
            return False
    try:
        parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(raw))
        except (ValueError, TypeError, IndexError):
            return False
    if parsed.tzinfo is not None:
        from zoneinfo import ZoneInfo
        parsed = parsed.astimezone(ZoneInfo("Asia/Yekaterinburg"))
    return parsed.date() >= threshold
