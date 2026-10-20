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
