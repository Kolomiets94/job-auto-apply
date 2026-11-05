from flask import Flask, jsonify, request
import hmac
import os
import threading
from datetime import datetime, timezone
from main import collect
from profit_ranker import rank_leads
from queue_store import enqueue, list_queue
from proposal_writer import make_proposal
from worker import run as run_worker

app=Flask(__name__)


def _authorized():
    expected = os.getenv("HUNTER_RUN_TOKEN", "").strip()
    provided = request.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(provided, "Bearer " + expected)


def _scheduler_authorized():
    expected = os.getenv("SCHEDULER_TOKEN", "").strip()
    provided = request.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(provided, "Bearer " + expected)


@app.get("/")
def home():
    return {"service":"Job + Freelance Hunter","status":"ok",
            "jobs":"/jobs","freelance":"/freelance","queue":"/queue"}

@app.get("/jobs")
def jobs():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(collect())

@app.get("/freelance")
def freelance():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    data=collect()
    leads=[x for x in data.get("items",[]) if x.get("category","").startswith("freelance") or x.get("category")=="freelance"]
    ranked=rank_leads(leads)
    for lead in ranked:
        enqueue(lead)
    return jsonify({"count":len(ranked),"items":[{**x,"proposal":make_proposal(x)} for x in ranked]})

@app.get("/queue")
def queue():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"items":list_queue()})

@app.post("/telegram/test")
def telegram_test():
    """Send one fixed Telegram connectivity test; protected by the hunter run token."""
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401

    from telegram_notifier import is_configured, send_message

    if not is_configured():
        return jsonify({"error": "telegram_not_configured"}), 503

    try:
        result = send_message("JobAutoApplyAlerts: тестовое подключение Telegram успешно.")
        return jsonify({"status": "sent", "parts": result.get("parts", 1)}), 200
    except Exception:
        app.logger.exception("Telegram connectivity test failed")
        return jsonify({"error": "telegram_send_failed"}), 502


@app.route("/telegram/test-form", methods=["GET", "POST"])
def telegram_test_form():
    """Phone-friendly one-message test, protected by a separate Render secret."""
    if request.method == "GET":
        return """<!doctype html><html lang="ru"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Telegram test</title><body style="font:16px sans-serif;max-width:34rem;margin:3rem auto;padding:0 1rem">
        <h2>Тест Telegram</h2><p>Введи TELEGRAM_TEST_TOKEN из Render. Пароль отправляется только в POST-запросе.</p>
        <form method="post"><input type="password" name="token" required autocomplete="off"
        placeholder="TELEGRAM_TEST_TOKEN" style="box-sizing:border-box;width:100%;padding:12px">
        <button style="margin-top:12px;padding:12px 18px">Отправить одно тестовое сообщение</button></form></body></html>"""

    expected = os.getenv("TELEGRAM_TEST_TOKEN", "").strip()
    provided = request.form.get("token", "").strip()
    if not expected or not hmac.compare_digest(provided, expected):
        return "Неверный токен или TELEGRAM_TEST_TOKEN не настроен.", 401

    from telegram_notifier import is_configured, send_message
    if not is_configured():
        return "Telegram не настроен: проверь TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID.", 503
    try:
        send_message("JobAutoApplyAlerts: тестовое подключение Telegram успешно.")
        return "Готово: тестовое сообщение отправлено в Telegram."
    except Exception:
        app.logger.exception("Telegram connectivity test failed")
        return "Не удалось отправить тест. Проверь логи Render.", 502


@app.post("/run")
def run_hunter():
    # Never allow anonymous internet requests to submit real job applications.
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(run_worker())


@app.post("/run/scheduled")
def run_scheduled():
    """A fast, idempotent trigger for a free external HTTP scheduler.

    The endpoint is intentionally draft-only until live sending, persistent
    storage, and the application channels have been reviewed together.
    """
    if not _scheduler_authorized():
        return jsonify({"error": "unauthorized"}), 401
    if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
        return jsonify({"error": "draft_mode_required"}), 409
    if not os.getenv("DATABASE_URL", "").strip():
        return jsonify({"error": "persistent_database_required"}), 503

    slot = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    try:
        from queue_store import _db
        with _db() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hunter_scheduled_runs "
                "(id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
                "completed_at TEXT, outcome TEXT)"
            )
            claim = connection.execute(
                "INSERT INTO hunter_scheduled_runs (id, started_at) "
                "VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
                (slot, datetime.now(timezone.utc).isoformat()),
            )
            claimed = claim.rowcount == 1
    except Exception:
        app.logger.exception("Could not claim scheduled run")
        return jsonify({"error": "schedule_store_unavailable"}), 503
    if not claimed:
        return jsonify({"status": "already_started", "hour_utc": slot}), 200

    def work():
        outcome = "failed"
        try:
            report = run_worker()
            stats = report.get("stats", {})
            print("[scheduled] complete", {
                key: stats.get(key) for key in
                ("found", "ranked", "drafted", "submitted", "notifications_sent")
            }, flush=True)
            outcome = "completed"
        except Exception:
            app.logger.exception("Scheduled draft run failed")
        finally:
            try:
                from queue_store import _db
                with _db() as connection:
                    connection.execute(
                        "UPDATE hunter_scheduled_runs SET completed_at=?,outcome=? WHERE id=?",
                        (datetime.now(timezone.utc).isoformat(), outcome, slot),
                    )
            except Exception:
                app.logger.exception("Could not record scheduled run outcome")

    threading.Thread(target=work, name="hunter-scheduled", daemon=True).start()
    print("[scheduled] claimed", slot, flush=True)
    return jsonify({"status": "started", "hour_utc": slot}), 202

@app.get("/health/db")
def database_health():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    try:
        from queue_store import _db
        with _db() as connection:
            connection.execute("SELECT 1").fetchone()
        return jsonify({"database": "ok"})
    except Exception:
        app.logger.exception("Database health check failed")
        return jsonify({"database": "unavailable"}), 503


@app.get("/health/db/status")
def public_database_status():
    """Read-only connectivity probe; never expose credentials or database details."""
    if not os.getenv("DATABASE_URL", "").strip():
        return jsonify({"database": "unavailable"}), 503
    try:
        from queue_store import _db
        with _db() as connection:
            connection.execute("SELECT 1").fetchone()
        return jsonify({"database": "ok"})
    except Exception:
        app.logger.warning("Public database connectivity check failed")
        return jsonify({"database": "unavailable"}), 503



@app.get("/dashboard")
def dashboard():
    """Read-only mobile dashboard. Protected with HTTP Basic Auth over HTTPS."""
    expected = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not expected:
        return jsonify({"error": "dashboard_password_not_configured"}), 503

    auth = request.authorization
    username = os.getenv("DASHBOARD_USER", "candidate").strip()
    provided_user = auth.username if auth and auth.username else ""
    provided_password = auth.password if auth and auth.password else ""
    if not (hmac.compare_digest(provided_user, username) and
            hmac.compare_digest(provided_password, expected)):
        response = jsonify({"error": "authentication_required"})
        response.status_code = 401
        response.headers["WWW-Authenticate"] = 'Basic realm="Job Auto Apply Dashboard"'
        response.headers["Cache-Control"] = "no-store"
        return response

    import json
    from flask import render_template_string
    rows = list_queue(limit=100)
    items = []
    counts = {}
    for row in rows:
        state = str(row.get("state") or "UNKNOWN")
        counts[state] = counts.get(state, 0) + 1
        try:
            payload = json.loads(row.get("payload") or "{}")
        except (TypeError, ValueError):
            payload = {}
        url = str(row.get("url") or payload.get("url") or "")
        if not url.startswith(("https://", "http://")):
            url = ""
        items.append({
            "title": str(row.get("title") or payload.get("title") or "Без названия"),
            "source": str(row.get("source") or payload.get("source") or "—"),
            "url": url,
            "score": row.get("score") or 0,
            "state": state,
            "updated": str(row.get("updated_at") or ""),
            "location": str(payload.get("location") or payload.get("country") or "Не указано"),
            "salary": str(payload.get("salary") or payload.get("salary_text") or "Не указана"),
            "eligibility": str(payload.get("eligibility_status") or payload.get("russia_eligibility") or "Не подтверждена — нужна проверка"),
        })

    page = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Job Auto Apply — вакансии</title>
<style>
:root{color-scheme:light dark}*{box-sizing:border-box}
body{font:16px/1.45 system-ui,-apple-system,sans-serif;margin:0;padding:18px;
max-width:850px;margin-inline:auto;background:Canvas;color:CanvasText}
h1{font-size:1.35rem;margin:.2rem 0}.muted{opacity:.72;font-size:.9rem}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
.stat{border:1px solid #8886;border-radius:12px;padding:8px 12px}
.card{border:1px solid #8886;border-radius:14px;padding:14px;margin:10px 0}
.card h2{font-size:1.04rem;margin:0 0 8px}
.meta{display:flex;gap:8px;flex-wrap:wrap;font-size:.9rem}
.pill{border:1px solid #8887;border-radius:99px;padding:2px 8px}
a{color:LinkText;overflow-wrap:anywhere}.line{margin:6px 0}
</style></head><body>
<h1>Job Auto Apply</h1>
<div class="muted">Последние {{ items|length }} записей · только просмотр, без отправки откликов</div>
<div class="stats">{% for state,count in counts.items() %}
<div class="stat"><b>{{ count }}</b><div class="muted">{{ state }}</div></div>
{% else %}<div class="muted">Очередь пока пуста</div>{% endfor %}</div>
{% for item in items %}
<article class="card"><h2>{% if item.url %}<a href="{{ item.url }}" target="_blank" rel="noopener noreferrer">{{ item.title }}</a>{% else %}{{ item.title }}{% endif %}</h2>
<div class="meta"><span class="pill">{{ item.state }}</span><span class="pill">Оценка: {{ item.score }}</span><span class="pill">{{ item.source }}</span></div>
<div class="line">🌍 {{ item.location }}</div><div class="line">💰 {{ item.salary }}</div>
<div class="line">Проверка работы из России: {{ item.eligibility }}</div>
<div class="muted">{{ item.updated }}</div></article>
{% endfor %}
</body></html>"""
    response = app.make_response(render_template_string(page, items=items, counts=counts))
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _start_one_shot_from_deploy():
    """Run a requested diagnostic pass once per ID, even across worker restarts."""
    marker = os.getenv("HUNTER_ONE_SHOT_ID", "").strip()
    if not marker:
        return
    import threading
    from datetime import datetime, timezone
    try:
        from queue_store import _db
        with _db() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hunter_one_shot_runs "
                "(id TEXT PRIMARY KEY, started_at TEXT NOT NULL)"
            )
            claim = connection.execute(
                "INSERT INTO hunter_one_shot_runs (id, started_at) "
                "VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
                (marker, datetime.now(timezone.utc).isoformat()),
            )
            claimed = claim.rowcount == 1
    except Exception:
        app.logger.exception("Could not claim one-shot hunter run")
        return
    if not claimed:
        return

    def run_in_background():
        try:
            report = run_worker()
            stats = report.get("stats", {})
            fields = ("found", "fresh_unique", "unique_checked", "ranked",
                      "job_ranked", "job_actionable", "drafted", "submitted",
                      "smtp_configured", "freelancehunt_token_configured",
                      "remote_job_identity_configured", "collection_errors")
            print("[one-shot] complete", {key: stats.get(key) for key in fields}, flush=True)
            drafts = [item for item in report.get("results", [])
                      if item.get("status") == "DRAFT"]
            for item in drafts[:5]:
                print("[one-shot] draft", repr({
                    key: item.get(key) for key in ("title", "source", "url", "proposal")
                }), flush=True)
        except Exception:
            app.logger.exception("One-shot hunter run failed")

    print("[one-shot] claimed", marker, flush=True)
    threading.Thread(target=run_in_background, name="hunter-one-shot", daemon=True).start()



def _start_telegram_diagnostic():
    """Send exactly one harmless connectivity test when explicitly enabled by env."""
    marker = os.getenv("TELEGRAM_DIAGNOSTIC_ID", "").strip()
    if not marker:
        return
    try:
        from queue_store import _db
        with _db() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS hunter_telegram_diagnostics "
                "(id TEXT PRIMARY KEY, started_at TEXT NOT NULL, outcome TEXT)"
            )
            claim = connection.execute(
                "INSERT INTO hunter_telegram_diagnostics (id, started_at) "
                "VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
                (marker, datetime.now(timezone.utc).isoformat()),
            )
            claimed = claim.rowcount == 1
    except Exception:
        app.logger.exception("Could not claim Telegram diagnostic")
        return
    if not claimed:
        return

    def send_test():
        outcome = "failed"
        try:
            from telegram_notifier import is_configured, send_message
            if not is_configured():
                print("[telegram-diagnostic] disabled: bot token or chat id missing", flush=True)
                outcome = "not_configured"
            else:
                send_message("JobAutoApplyAlerts: проверка подключения Telegram. Это тестовое сообщение.")
                print("[telegram-diagnostic] sent successfully", flush=True)
                outcome = "sent"
        except Exception as exc:
            # Never print exception text: request URLs may contain the bot token.
            print("[telegram-diagnostic] failed:", type(exc).__name__, flush=True)
        finally:
            try:
                from queue_store import _db
                with _db() as connection:
                    connection.execute(
                        "UPDATE hunter_telegram_diagnostics SET outcome=? WHERE id=?",
                        (outcome, marker),
                    )
            except Exception:
                app.logger.exception("Could not record Telegram diagnostic outcome")

    threading.Thread(target=send_test, name="telegram-diagnostic", daemon=True).start()
    print("[telegram-diagnostic] claimed", marker, flush=True)


_start_telegram_diagnostic()

_start_one_shot_from_deploy()
