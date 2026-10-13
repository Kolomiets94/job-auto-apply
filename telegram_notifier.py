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

    # Telegram sendMessage has a 4096-character limit. Split on line boundaries.\n    chunks = []\n    remaining = str(text)\n    while remaining:\n        if len(remaining) <= 3900:\n            chunks.append(remaining)\n            break\n        boundary = remaining.rfind("\\n", 0, 3900)\n        if boundary < 1000:\n            boundary = 3900\n        chunks.append(remaining[:boundary])\n        remaining = remaining[boundary:].lstrip("\\n")\n    for index, chunk in enumerate(chunks):\n        response = requests.post(\n            f"https://api.telegram.org/bot{token}/sendMessage",\n            json={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},\n            timeout=timeout,\n        )\n        response.raise_for_status()\n    return {"status": "SENT", "parts": len(chunks)}


def send_notification(notification: Dict, timeout: int = 10) -> Dict[str, str]:
    return send_message(notification.get("message", ""), timeout=timeout)
