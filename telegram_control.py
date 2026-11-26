"""Inbound Telegram commands for recording outreach outcomes.

Only the configured private chat can inspect/update the outreach journal.
This module never sends applications or messages to employers.
"""
import os
import re

from queue_store import (
    FEEDBACK_REASONS,
    OUTREACH_STATES,
    list_outreach,
    resolve_outreach_id,
    update_outreach_status,
)
from telegram_notifier import send_message


_REASON_LABELS = {
    "skills_gap": "не совпали навыки",
    "experience_gap": "недостаточно опыта",
    "location_restriction": "ограничение по локации",
    "work_authorization": "право на работу",
    "language": "язык",
    "salary": "зарплата",
    "role_mismatch": "несовпадение роли",
    "position_filled": "позиция закрыта",
    "other": "другая причина",
}


def _reply(text):
    return send_message(text)


def _help_text():
    return (
        "Управление журналом Job Hunter\n"
        "/outreach — последние 10 обращений\n"
        "/scheduled_queue — состояние очереди планировщика\n"
        "/set ID STATUS — изменить статус\n"
        "/set ID REJECTED REASON — отказ с категорией причины\n\n"
        "Статусы: " + ", ".join(OUTREACH_STATES) + "\n"
        "Причины: " + ", ".join(FEEDBACK_REASONS) + "\n"
        "ID — короткий префикс из списка /outreach (не менее 8 символов)."
    )


def _outreach_text():
    items = list_outreach(limit=10)
    if not items:
        return "Журнал обращений пока пуст."
    lines = ["Последние обращения (ID · статус · компания):"]
    for item in items:
        company = re.sub(r"[\\r\\n]+", " ", str(item.get("company") or "Без названия"))
        company = company[:90]
        lines.append(
            f"{str(item.get('id') or '')[:12]} · "
            f"{item.get('status') or 'UNKNOWN'} · {company}"
        )
    lines.append("Изменить: /set ID STATUS [REASON]")
    return "\\n".join(lines)


def _scheduled_queue_text():
    enabled = os.getenv("HUNTER_SCHEDULED_QUEUE_ENABLED", "").strip().lower() in ("1", "true", "yes")
    if not enabled:
        return "Очередь планировщика выключена. Сейчас используется legacy-режим."
    try:
        from scheduled_tasks import scheduled_task_summary
        summary = scheduled_task_summary(limit=5)
    except Exception:
        return "Не удалось прочитать очередь планировщика. Подробности доступны в логах сервиса."
    counts = summary.get("status_counts") or {}
    lines = [
        "Очередь планировщика: включена",
        "Всего задач: " + str(int(summary.get("total", 0))),
    ]
    if counts:
        lines.append("Статусы: " + ", ".join(
            f"{str(status)[:24]}={int(count)}"
            for status, count in sorted(counts.items())
        ))
    else:
        lines.append("Задач пока нет.")
    recent = summary.get("recent_tasks") or []
    if recent:
        lines.append("Последние задачи:")
        for task in recent[:5]:
            lines.append(
                f"{str(task.get('id') or '')[:12]} · "
                f"{str(task.get('status') or 'UNKNOWN')[:16]} · "
                f"попыток: {int(task.get('attempts', 0))}"
            )
    return "\n".join(lines)


def handle_update(update):
    """Process a Telegram webhook update from the configured chat only."""
    configured_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip() or os.getenv("CHAT_ID", "").strip()
    message = update.get("message") if isinstance(update, dict) else None
    if not configured_chat:
        return {"status": "ignored", "reason": "chat_not_configured"}
    if not isinstance(message, dict):
        return {"status": "ignored", "reason": "no_message"}
    chat = message.get("chat") or {}
    if str(chat.get("id", "")) != configured_chat:
        return {"status": "ignored", "reason": "chat_mismatch"}
    text = str(message.get("text") or "").strip()
    if not text.startswith("/"):
        return {"status": "ignored", "reason": "not_a_command"}

    parts = text.split()
    command = parts[0].split("@", 1)[0].lower()
    if command in ("/start", "/help"):
        _reply(_help_text())
        return {"status": "replied", "command": "start_or_help"}
    if command == "/outreach":
        _reply(_outreach_text())
        return {"status": "replied", "command": "outreach"}
    if command in ("/scheduled_queue", "/queue_status"):
        _reply(_scheduled_queue_text())
        return {"status": "replied", "command": "scheduled_queue"}
    if command != "/set":
        _reply("Неизвестная команда. Используйте /help.")
        return {"status": "replied", "command": "unknown"}
    if len(parts) not in (3, 4):
        _reply("Формат: /set ID STATUS [REASON]. Подробности: /help.")
        return {"status": "replied", "command": "set_invalid"}

    prefix, status = parts[1], parts[2].upper()
    reason = parts[3].lower() if len(parts) == 4 else None
    if status not in OUTREACH_STATES:
        _reply("Неизвестный статус. Допустимые: " + ", ".join(OUTREACH_STATES))
        return {"status": "replied", "command": "set_invalid_status"}
    if reason is not None and (status != "REJECTED" or reason not in FEEDBACK_REASONS):
        _reply("Для REJECTED укажите одну из категорий: " + ", ".join(FEEDBACK_REASONS))
        return {"status": "replied", "command": "set_invalid_reason"}
    try:
        outreach_id = resolve_outreach_id(prefix)
        if outreach_id is None:
            _reply("Обращение с таким ID не найдено. Обновите список командой /outreach.")
            return {"status": "replied", "command": "set_not_found"}
        update_outreach_status(outreach_id, status, feedback_reason=reason)
    except ValueError as exc:
        _reply(str(exc))
        return {"status": "replied", "command": "set_invalid"}
    _reply(f"Записано: {status}" + (f" · {_REASON_LABELS[reason]}" if reason else "") + ".")
    return {"status": "updated", "command": "set"}
