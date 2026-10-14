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
