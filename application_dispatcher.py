"""Application dispatcher.

Prefers supported browser-based application forms. Uses direct email only
when a vacancy has no supported browser form and explicitly provides an
application email address. Paid bids and security challenges are never
silently accepted or bypassed.
"""

import os
import re
from urllib.parse import urlsplit, unquote

from application_schedule import application_time_allowed
from browser_apply import dispatch_browser
from freelancehunt_adapter import add_bid


def _send_email(lead, proposal):
    email = lead.get("apply_email")
    apply_url = str(lead.get("apply_url") or "")
    if not email and urlsplit(apply_url).scheme == "mailto":
        email = unquote(urlsplit(apply_url).path)
    if not email:
        return None

    if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", str(email)):
        return {"status": "NEEDS_CONFIRMATION", "reason": "invalid_application_email"}

    if os.getenv("AUTO_SEND_EMAIL", "0") != "1":
        return {"status": "SHORTLISTED", "reason": "email_send_disabled"}

    from gmail_api import is_configured, send_message
    if not is_configured():
        return {"status": "SHORTLISTED", "reason": "gmail_api_not_configured"}
    prefix = "Application" if lead.get("language") == "en" else "Отклик"
    subject = f"{prefix}: {lead.get('title', 'проект')}"
    body = proposal + "\n\nGitHub: https://github.com/Kolomiets94\n" + str(lead.get("url") or "")
    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}
    try:
        send_message(str(email), subject, body)
    except Exception as exc:
        return {"status": "FAILED", "reason": "gmail_api_" + type(exc).__name__}
    return {"status": "SUBMITTED", "reason": "email_sent_via_gmail_api"}


def dispatch(lead, proposal):
    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}

    if lead.get("paid_bid") is True:
        return {"status": "SKIPPED", "reason": "paid_bid"}

    # Freelance bids require a separately reviewed price and scope. Keep them
    # out of unattended dispatch even if an environment flag/token is present.
    if str(lead.get("source") or "").lower() in {"freelancehunt", "fl_ru", "freelance_ru"}:
        return {"status": "SKIPPED", "reason": "freelance_submission_not_authorized"}

    # The user authorized automatic applications. Prefer clicking through the
    # supported website form (Playwright/Chromium); do not require Gmail/SMTP.
    if lead.get("source") == "freelancehunt" and lead.get("can_api_bid"):
        return add_bid(lead, proposal)

    browser_result = dispatch_browser(lead, proposal)
    if browser_result.get("reason") != "unsupported_browser_source":
        return browser_result

    # Email is a last-resort channel only when the site has no supported form.
    email_result = _send_email(lead, proposal)
    if email_result is not None:
        return email_result

    if lead.get("apply_url"):
        return {"status": "NEEDS_CONFIRMATION", "reason": "external_application_form_not_supported",
                "apply_url": lead["apply_url"]}
    return {"status": "NEEDS_CONFIRMATION", "reason": "no_free_direct_channel"}
