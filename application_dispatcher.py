"""Application dispatcher.

Uses free direct email when configured, otherwise supported browser automation.
Paid bids and security challenges are never silently accepted or bypassed.
"""

import os
import smtplib
import re
from urllib.parse import urlsplit, unquote
from email.message import EmailMessage

from application_schedule import application_time_allowed
from browser_apply import dispatch_browser
from freelancehunt_adapter import add_bid
from external_form_apply import apply_external


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


def _is_hh_lead(lead):
    if str(lead.get("source") or lead.get("site") or "").strip().lower() == "hh":
        return True
    for value in (lead.get("url"), lead.get("apply_url")):
        host = (urlsplit(str(value or "")).hostname or "").lower()
        if host == "hh.ru" or host.endswith(".hh.ru"):
            return True
    return False


def dispatch(lead, proposal):
    # HH applicant-side API access is unavailable, but the authenticated
    # browser flow can submit applications. It fails closed without a session,
    # matching résumé, known answers, or a confirmed post-submit state.
    if _is_hh_lead(lead):
        return dispatch_browser(lead, proposal)

    if not application_time_allowed():
        return {"status": "SKIPPED", "reason": "outside_application_hours"}

    if lead.get("paid_bid") is True:
        return {"status": "SKIPPED", "reason": "paid_bid"}

    # FL.ru's RSS does not expose whether a bid is free. Never risk a paid bid:
    # only proceed when a source explicitly verifies free access.
    if lead.get("source") == "fl_ru" and lead.get("free_to_apply") is not True:
        return {"status": "NEEDS_CONFIRMATION", "reason": "no_free_direct_channel", "detail": "FL.ru RSS does not verify free bid access"}

    # The user authorized automatic applications; report outcomes via the worker.
    if lead.get("source") == "freelancehunt" and lead.get("can_api_bid"):
        return add_bid(lead, proposal)

    email_result = _send_email(lead, proposal)
    if email_result is not None:
        return email_result

    browser_result = dispatch_browser(lead, proposal)
    if browser_result.get("reason") != "unsupported_browser_source":
        return browser_result

    # Use the conservative allowlisted handler for supported employer ATS forms.
    # AUTO_BROWSER_APPLY and the worker's DRY_RUN gate remain authoritative.
    if lead.get("apply_url"):
        return apply_external(lead, proposal)
    return {"status": "NEEDS_CONFIRMATION", "reason": "no_free_direct_channel"}
