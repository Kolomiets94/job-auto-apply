"""Application dispatcher.

Prefers supported browser-based application forms. Uses direct email only
when a vacancy has no supported browser form and explicitly provides an
application email address. Paid bids and security challenges are never
silently accepted or bypassed.
"""

import os
import smtplib
import re
from urllib.parse import urlsplit, unquote
from email.message import EmailMessage

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

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    if not all((host, user, password)):
        return {"status": "SHORTLISTED", "reason": "smtp_not_configured"}

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = email
    prefix = "Application" if lead.get("language") == "en" else "Отклик"
    msg["Subject"] = f"{prefix}: {lead.get('title', 'проект')}"
    msg.set_content(proposal + "\n\nGitHub: https://github.com/Kolomiets94\n"
                    + str(lead.get("url") or ""))

    with smtplib.SMTP_SSL(
        host,
        int(os.getenv("SMTP_PORT") or "465"),
        timeout=30,
    ) as smtp:
        smtp.login(user, password)
        if not application_time_allowed():
            return {"status": "SKIPPED", "reason": "outside_application_hours"}
        rejected = smtp.send_message(msg)
        if rejected:
            return {"status": "FAILED", "reason": "email_recipient_rejected"}

    return {"status": "SUBMITTED", "reason": "email_sent"}


def dispatch(lead, proposal):
    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}

    if lead.get("paid_bid") is True:
        return {"status": "SKIPPED", "reason": "paid_bid"}

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
