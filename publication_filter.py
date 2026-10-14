"""Fail-closed publication-date filter for job applications."""
import os
from datetime import datetime, date, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Yekaterinburg")


def is_new_publication(lead):
    cutoff = os.getenv("MIN_PUBLICATION_DATE", "").strip()
    if not cutoff:
        return True
    if cutoff.lower() == "today":
        threshold = datetime.now(LOCAL_TZ).date()
    else:
        try:
            threshold = date.fromisoformat(cutoff)
        except ValueError:
            raise ValueError("MIN_PUBLICATION_DATE must be YYYY-MM-DD or today")
    raw = lead.get("published") or lead.get("published_at") or lead.get("publication_date")
    if raw is None or str(raw).strip() == "":
        return False
    if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.strip().isdigit()):
        try:
            number = float(raw)
            if number > 1e11:
                number /= 1000
            return datetime.fromtimestamp(number, tz=timezone.utc).astimezone(LOCAL_TZ).date() >= threshold
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
        parsed = parsed.astimezone(LOCAL_TZ)
    return parsed.date() >= threshold
