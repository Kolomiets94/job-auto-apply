"""Telegram delivery for top-ranked leads.

Configuration is entirely via environment variables:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

If either variable is absent, sending is disabled and the worker continues normally.
"""

import os
from typing import Dict

import requests


def is_configured() -> bool:
    return bool(
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        and os.getenv("TELEGRAM_CHAT_ID", "").strip()
    )


def send_message(text: str, timeout: int = 10) -> Dict[str, str]:
    """Send a plain-text Telegram message, or return DISABLED if not configured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        return {"status": "DISABLED", "reason": "telegram_not_configured"}

    # Keep every message below Telegram's 4096-character limit.
    chunks = []
    remaining = str(text)
    while remaining:
        if len(remaining) <= 3900:
            chunks.append(remaining)
            break
        boundary = remaining.rfind("\n", 0, 3900)
        if boundary < 1000:
            boundary = 3900
        chunks.append(remaining[:boundary])
        remaining = remaining[boundary:].lstrip("\n")
    for chunk in chunks:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=timeout,
        )
        if not response.ok:
            # Telegram's error description is safe to log; never include the request URL,
            # which contains the bot token.
            try:
                detail = response.json().get("description", "")
            except (ValueError, AttributeError):
                detail = ""
            print(
                f"[telegram] API rejected message: HTTP {response.status_code}"
                + (f" — {str(detail)[:240]}" if detail else ""),
                flush=True,
            )
            response.raise_for_status()
    return {"status": "SENT", "parts": len(chunks)}


def send_notification(notification: Dict, timeout: int = 10) -> Dict[str, str]:
    return send_message(notification.get("message", ""), timeout=timeout)
