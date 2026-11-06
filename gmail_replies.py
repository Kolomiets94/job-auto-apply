"""Forward unread replies to application emails from Gmail to the existing Telegram alerts chat.

Only messages whose subject contains the application's generated subject prefix
("Отклик:" or "Application:") are forwarded. Unrelated inbox mail is untouched.
Uses stdlib only; marks a message read only after Telegram confirms delivery.
"""
from __future__ import annotations

import email
import json
import imaplib
import os
import re
import urllib.parse
import urllib.request
from email.header import decode_header, make_header
from email.message import Message


def _env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _plain_text(message: Message, limit: int = 500) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() != "text/plain":
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        value = re.sub(r"\s+", " ", payload.decode(charset, errors="replace")).strip()
        return value[:limit] + ("…" if len(value) > limit else "")
    return ""


def _telegram_send(token: str, chat_id: str, text: str) -> None:
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Telegram returned HTTP {response.status}")
        result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError("Telegram did not accept the notification")


def main() -> int:
    user = _env("IMAP_USER", _env("SMTP_USER"))
    password = _env("IMAP_PASSWORD", _env("SMTP_PASSWORD"))
    token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")
    if not all((user, password, token, chat_id)):
        print("[gmail-replies] skipped: Gmail/Telegram secrets are not configured")
        return 0

    host = _env("IMAP_HOST", "imap.gmail.com")
    port = int(_env("IMAP_PORT", "993"))
    client = None
    delivered = 0
    scanned = 0
    try:
        client = imaplib.IMAP4_SSL(host, port)
        client.login(user, password)
        status, _ = client.select("INBOX")
        if status != "OK":
            raise RuntimeError("Could not open Gmail INBOX")
        status, data = client.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Gmail unread-message search failed")

        uids = data[0].split() if data and data[0] else []
        print(f"[gmail-replies] unread messages to inspect: {len(uids)}")
        for uid in uids:
            status, rows = client.uid("fetch", uid, "(BODY.PEEK[])")
            if status != "OK":
                continue
            raw = next((row[1] for row in rows if isinstance(row, tuple)), None)
            if not raw:
                continue
            scanned += 1
            msg = email.message_from_bytes(raw)
            subject = _decode(msg.get("Subject"))
            # Match only replies to the subjects created by application_dispatcher.py.
            if not re.search(r"(?:Отклик|Application):", subject, flags=re.IGNORECASE):
                continue

            sender = _decode(msg.get("From")) or "(отправитель не указан)"
            date = _decode(msg.get("Date"))
            snippet = _plain_text(msg)
            text = (
                "📩 Ответ на отклик в Gmail\n"
                f"От: {sender}\n"
                f"Тема: {subject}\n"
                + (f"Дата: {date}\n" if date else "")
                + (f"Фрагмент: {snippet}" if snippet else "Текст письма не удалось извлечь.")
            )
            try:
                _telegram_send(token, chat_id, text)
            except Exception as exc:
                print(f"[gmail-replies] Telegram delivery failed: {type(exc).__name__}")
                continue
            # Do not touch the message until Telegram accepted the notification.
            client.uid("store", uid, "+FLAGS", "(\\Seen)")
            delivered += 1

        print(f"[gmail-replies] inspected={scanned}; application replies forwarded={delivered}")
        return 0
    except imaplib.IMAP4.error as exc:
        print(f"[gmail-replies] Gmail IMAP error: {exc}")
        return 1
    except Exception as exc:
        print(f"[gmail-replies] failed: {type(exc).__name__}: {exc}")
        return 1
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
