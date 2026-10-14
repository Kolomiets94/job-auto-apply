from flask import Flask, jsonify, request
import hmac
import os
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
