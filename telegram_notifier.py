"""Telegram delivery for top-ranked leads.

Configuration supports the current names and legacy project names:
- TELEGRAM_BOT_TOKEN (fallback: BOT_TOKEN)
- TELEGRAM_CHAT_ID (fallback: CHAT_ID)

If either value is absent, sending is disabled and the worker continues normally.
"""

import os
from typing import Dict

import requests


def _telegram_credentials():
    # config.py in this repository historically exposed BOT_TOKEN. Accept it
    # as a fallback so existing Render Environment settings keep working.
    token = (
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        or os.getenv("BOT_TOKEN", "").strip()
    )
    chat_id = (
        os.getenv("TELEGRAM_CHAT_ID", "").strip()
        or os.getenv("CHAT_ID", "").strip()
    )
    return token, chat_id


def is_configured() -> bool:
    token, chat_id = _telegram_credentials()
    return bool(token and chat_id)


def send_message(text: str, timeout: int = 10) -> Dict[str, str]:
    """Send a plain-text Telegram message, or return DISABLED if not configured."""
    token, chat_id = _telegram_credentials()

    if not token or not chat_id:
        return {"status": "DISABLED", "reason": "telegram_not_configured"}

    # Keep every message below Telegram's 4096-character limit.
    chunks = []
    remaining = str(text)
    while remaining:
        if len(remaining) <= 3900:
            chunks.append(remaining)
            break
        boundary = remaining.rfind("\\n", 0, 3900)
        if boundary < 1000:
            boundary = 3900
        chunks.append(remaining[:boundary])
        remaining = remaining[boundary:].lstrip("\\n")
    for chunk in chunks:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=timeout,
        )
        response.raise_for_status()
        # Telegram may return HTTP 200 with {"ok": false}; surface that too.
        payload = response.json()
        if not payload.get("ok", False):
            description = str(payload.get("description") or "Telegram API rejected message")
            raise RuntimeError(f"Telegram API error: {description[:240]}")
    return {"status": "SENT", "parts": len(chunks)}


def send_notification(notification: Dict, timeout: int = 10) -> Dict[str, str]:
    return send_message(notification.get("message", ""), timeout=timeout)
