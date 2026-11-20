from flask import Flask, jsonify, request
import hmac
import os
import threading
from datetime import datetime, timezone
from main import collect
from profit_ranker import rank_leads, FREELANCE_SOURCES
from queue_store import enqueue, list_queue, list_outreach, update_outreach_status, build_outcome_feedback_report
from proposal_writer import make_proposal
from worker import run as run_worker

app=Flask(__name__)


_telegram_setup_lock = threading.Lock()
_telegram_setup_done = False


@app.before_request
def _complete_one_time_telegram_setup():
    """Register the fixed Telegram webhook once when Render checks the service health."""
    global _telegram_setup_done
    if request.path != "/" or _telegram_setup_done:
        return None
    with _telegram_setup_lock:
        if _telegram_setup_done:
            return None
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
        secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if not token or len(secret) < 32:
            app.logger.warning("Telegram one-time setup skipped: required configuration missing")
            return None
        try:
            import requests
            response = requests.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={
                    "url": "https://job-freelance-hunter.onrender.com/telegram/webhook",
                    "secret_token": secret,
                    "allowed_updates": ["message"],
                },
                timeout=15,
            )
            response.raise_for_status()
            if response.json().get("ok"):
                _telegram_setup_done = True
                app.logger.info("Telegram webhook registered by one-time setup")
            else:
                app.logger.warning("Telegram one-time webhook setup was rejected")
        except Exception:
            app.logger.exception("Telegram one-time webhook setup request failed")
    return None


def _authorized():
    expected = os.getenv("HUNTER_RUN_TOKEN", "").strip()
    provided = request.headers.get("Authorization", "")
    return bool(expected) and hmac.compare_digest(provided, "Bearer " + expected)


def _scheduler_claims():
    """Return verified GitHub Actions OIDC claims for this repository/workflow."""
    provided = request.headers.get("Authorization", "")
    if not provided.startswith("Bearer "):
        return None
    token = provided[7:].strip()
    if not token:
        return None
    try:
        import jwt
        from jwt import PyJWKClient
        jwks = PyJWKClient("https://token.actions.githubusercontent.com/.well-known/jwks")
        signing_key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience="https://job-freelance-hunter.onrender.com/run/scheduled",
            issuer="https://token.actions.githubusercontent.com",
        )
        valid = (
            claims.get("repository") == "Kolomiets94/job-auto-apply"
            and claims.get("ref") == "refs/heads/main"
            and claims.get("workflow_ref") ==
                "Kolomiets94/job-auto-apply/.github/workflows/hourly-job-hunter.yml@refs/heads/main"
            and claims.get("event_name") in ("schedule", "workflow_dispatch")
        )
        return claims if valid else None
    except Exception:
        app.logger.warning("Scheduled request rejected: invalid GitHub OIDC token")
        return None


@app.get("/")
def home():
    return {"service":"Job + Freelance Hunter","status":"ok",
            "jobs":"/jobs","freelance":"/freelance","queue":"/queue"}

@app.get("/jobs")
def jobs():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    data = collect()
    data["items"] = [
        item for item in data.get("items", [])
        if str(item.get("source") or "").lower() not in FREELANCE_SOURCES
    ]
    data["count"] = len(data["items"])
    return jsonify(data)

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

@app.get("/outreach")
def outreach():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    try:
        limit = max(1, min(int(request.args.get("limit", "100")), 500))
    except ValueError:
        return jsonify({"error": "invalid_limit"}), 400
    return jsonify({
        "items": list_outreach(limit=limit),
        "feedback_report": build_outcome_feedback_report(),
    })


@app.post("/outreach/<outreach_id>/status")
def update_outreach(outreach_id):
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "json_object_required"}), 400
    status = payload.get("status")
    reason = payload.get("feedback_reason")
    try:
        updated = update_outreach_status(
            outreach_id,
            status,
            feedback_reason=reason,
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    if not updated:
        return jsonify({"error": "outreach_not_found"}), 404
    return jsonify({"status": "updated", "outreach_id": outreach_id})


@app.post("/telegram/register-webhook")
def register_telegram_webhook():
    """Register this service's fixed Telegram webhook without exposing bot credentials."""
    setup_key = os.getenv("TELEGRAM_WEBHOOK_SETUP_KEY", "").strip()
    setup_provided = request.headers.get("X-Telegram-Setup-Key", "")
    setup_authorized = bool(setup_key) and hmac.compare_digest(setup_provided, setup_key)
    if not (_authorized() or setup_authorized):
        return jsonify({"error": "unauthorized"}), 401
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not token or not secret:
        return jsonify({"error": "telegram_configuration_missing"}), 503
    if len(secret) < 32:
        return jsonify({"error": "webhook_secret_too_short"}), 503
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": "https://job-freelance-hunter.onrender.com/telegram/webhook",
                "secret_token": secret,
                "allowed_updates": ["message"],
            },
            timeout=15,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not result.get("ok"):
            app.logger.warning("Telegram webhook registration was rejected by Telegram")
            return jsonify({"error": "telegram_registration_failed"}), 502
    except Exception:
        app.logger.exception("Telegram webhook registration request failed")
        return jsonify({"error": "telegram_registration_failed"}), 502
    return jsonify({"status": "registered", "webhook": "/telegram/webhook"})


@app.post("/telegram/webhook")
def telegram_webhook():
    """Receive authenticated Telegram bot commands; never sends employer messages."""
    expected = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        return jsonify({"error": "unauthorized"}), 401
    update = request.get_json(silent=True)
    if not isinstance(update, dict):
        return jsonify({"error": "invalid_update"}), 400
    try:
        from telegram_control import handle_update
        handle_update(update)
    except Exception:
        app.logger.exception("Telegram control update failed")
        return jsonify({"error": "update_failed"}), 500
    return jsonify({"ok": True})


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
    claims = _scheduler_claims()
    if not claims:
        return jsonify({"error": "unauthorized"}), 401
    if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
        return jsonify({"error": "draft_mode_required"}), 409
    if not os.getenv("DATABASE_URL", "").strip():
        return jsonify({"error": "persistent_database_required"}), 503

    hour_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    if claims.get("event_name") == "workflow_dispatch":
        run_id = str(claims.get("run_id") or "").strip()
        run_attempt = str(claims.get("run_attempt") or "").strip()
        if not run_id.isdigit() or not run_attempt.isdigit():
            return jsonify({"error": "manual_run_identity_missing"}), 401
        slot = f"manual:{run_id}:{run_attempt}"
    else:
        slot = hour_utc
        run_id = ""
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
    response = {"status": "started", "hour_utc": hour_utc}
    if run_id:
        response["run_id"] = run_id
    return jsonify(response), 202

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


_start_one_shot_from_deploy()
