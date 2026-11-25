"""Forward unread application replies from Gmail API to Telegram."""
from __future__ import annotations
import email, re
from email.header import decode_header, make_header
from email.message import Message
from gmail_api import get_raw_message, list_unread, mark_read
from telegram_notifier import send_message
from ai_assistant import analyze_application_reply


def _decode(value: str | None) -> str:
    if not value: return ""
    try: return str(make_header(decode_header(value)))
    except Exception: return value


def _plain_text(message: Message, limit: int = 500) -> str:
    parts=message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_maintype()=="multipart" or part.get_content_disposition()=="attachment": continue
        if part.get_content_type()!="text/plain": continue
        payload=part.get_payload(decode=True)
        if not payload: continue
        charset=part.get_content_charset() or "utf-8"
        value=re.sub(r"\s+"," ",payload.decode(charset,errors="replace")).strip()
        return value[:limit]+("…" if len(value)>limit else "")
    return ""


def main() -> int:
    delivered=scanned=0
    try:
        ids=list_unread(50)
        print(f"[gmail-replies] unread messages to inspect: {len(ids)}")
        for message_id in ids:
            raw=get_raw_message(message_id)
            if not raw: continue
            scanned+=1
            msg=email.message_from_bytes(raw)
            subject=_decode(msg.get("Subject"))
            if not re.search(r"(?:Отклик|Application):",subject,flags=re.IGNORECASE): continue
            sender=_decode(msg.get("From")) or "(отправитель не указан)"
            date=_decode(msg.get("Date"))
            snippet=_plain_text(msg)
            text=("📩 Ответ на отклик в Gmail\n"+f"От: {sender}\nТема: {subject}\n"
                  +(f"Дата: {date}\n" if date else "")
                  +(f"Фрагмент: {snippet}" if snippet else "Текст письма не удалось извлечь."))

            # GPT analysis is advisory only. It cannot send a reply or change Gmail state.
            try:
                analysis = analyze_application_reply(subject, sender, snippet)
                if analysis:
                    text += "\n\n🤖 Анализ GPT (проверь перед действием):\n" + analysis
            except Exception as exc:
                print(f"[gmail-replies] GPT analysis unavailable: {type(exc).__name__}")

            try: send_message(text)
            except Exception as exc:
                print(f"[gmail-replies] Telegram delivery failed: {type(exc).__name__}")
                continue
            mark_read(message_id)
            delivered+=1
        print(f"[gmail-replies] inspected={scanned}; application replies forwarded={delivered}")
        return 0
    except Exception as exc:
        print(f"[gmail-replies] Gmail API error: {type(exc).__name__}")
        return 1


if __name__=="__main__": raise SystemExit(main())
