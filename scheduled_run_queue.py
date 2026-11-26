"""Durable, lease-based queue for draft-only scheduled hunter runs."""

import os
import threading
import time
from datetime import datetime, timedelta, timezone

LEASE_SECONDS = 300
POLL_SECONDS = 5
HEARTBEAT_SECONDS = 30
_start_lock = threading.Lock()
_started = False


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat()


def ensure_schema():
    from queue_store import _db

    with _db() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS hunter_scheduled_runs ("
            "id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT, "
            "outcome TEXT, status TEXT NOT NULL DEFAULT 'queued', "
            "lease_until TEXT, attempts INTEGER NOT NULL DEFAULT 0)"
        )
        if hasattr(connection, "conn"):
            columns = {
                row[0] for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='hunter_scheduled_runs'"
                ).fetchall()
            }
        else:
            columns = {row[1] for row in connection.execute(
                "PRAGMA table_info(hunter_scheduled_runs)"
            ).fetchall()}
        status_was_missing = "status" not in columns
        migrations = {
            "status": "TEXT NOT NULL DEFAULT 'queued'",
            "lease_until": "TEXT",
            "attempts": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in migrations.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE hunter_scheduled_runs ADD COLUMN {column} {definition}"
                )
        if status_was_missing:
            # Do not replay historical daemon-thread runs: their side effects may
            # already have happened even if their completion marker was lost.
            connection.execute(
                "UPDATE hunter_scheduled_runs SET status=CASE "
                "WHEN completed_at IS NOT NULL THEN 'completed' ELSE 'abandoned' END"
            )


def enqueue_run(run_id):
    ensure_schema()
    from queue_store import _db

    with _db() as connection:
        result = connection.execute(
            "INSERT INTO hunter_scheduled_runs "
            "(id, started_at, status, attempts) VALUES (?, ?, 'queued', 0) "
            "ON CONFLICT (id) DO NOTHING",
            (run_id, _iso(_now())),
        )
        return result.rowcount == 1


def claim_next_run():
    ensure_schema()
    from queue_store import _db

    now = _now()
    now_text = _iso(now)
    lease_text = _iso(now + timedelta(seconds=LEASE_SECONDS))
    with _db() as connection:
        result = connection.execute(
            "UPDATE hunter_scheduled_runs SET status='running', lease_until=?, "
            "attempts=attempts+1 WHERE id=(SELECT id FROM hunter_scheduled_runs "
            "WHERE status='queued' OR (status='running' AND lease_until<?) "
            "ORDER BY started_at LIMIT 1) AND "
            "(status='queued' OR (status='running' AND lease_until<?)) "
            "RETURNING id",
            (lease_text, now_text, now_text),
        )
        row = result.fetchone()
        return row[0] if row else None


def renew_lease(run_id):
    from queue_store import _db

    lease_text = _iso(_now() + timedelta(seconds=LEASE_SECONDS))
    with _db() as connection:
        result = connection.execute(
            "UPDATE hunter_scheduled_runs SET lease_until=? "
            "WHERE id=? AND status='running'",
            (lease_text, run_id),
        )
        return result.rowcount == 1


def finish_run(run_id, outcome):
    from queue_store import _db

    with _db() as connection:
        connection.execute(
            "UPDATE hunter_scheduled_runs SET status=?, completed_at=?, "
            "outcome=?, lease_until=NULL WHERE id=?",
            (outcome, _iso(_now()), outcome, run_id),
        )


def process_run(run_id, run_worker):
    stop_heartbeat = threading.Event()

    def heartbeat():
        while not stop_heartbeat.wait(HEARTBEAT_SECONDS):
            try:
                if not renew_lease(run_id):
                    print(f"[scheduled] lease lost for {run_id}", flush=True)
                    return
            except Exception:
                print(f"[scheduled] lease renewal failed for {run_id}", flush=True)

    heartbeat_thread = threading.Thread(
        target=heartbeat, name="hunter-scheduled-heartbeat", daemon=True
    )
    heartbeat_thread.start()
    outcome = "failed"
    try:
        report = run_worker(force_dry_run=True)
        stats = report.get("stats", {})
        print(
            "[scheduled] complete",
            {key: stats.get(key) for key in
             ("found", "ranked", "drafted", "submitted", "notifications_sent")},
            flush=True,
        )
        outcome = "completed"
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Scheduled draft run failed")
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        try:
            finish_run(run_id, outcome)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Could not record scheduled run outcome"
            )


def _worker_loop(run_worker, stop_event):
    while not stop_event.is_set():
        if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
            stop_event.wait(POLL_SECONDS)
            continue
        try:
            run_id = claim_next_run()
            if run_id:
                print(f"[scheduled] claimed durable task {run_id}", flush=True)
                process_run(run_id, run_worker)
                continue
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Scheduled task poll failed")
        stop_event.wait(POLL_SECONDS)


def start_worker(run_worker):
    """Start a per-process poller; database leases coordinate multiple web workers."""
    global _started
    if not os.getenv("DATABASE_URL", "").strip():
        return False
    if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
        return False
    with _start_lock:
        if _started:
            return True
        ensure_schema()
        thread = threading.Thread(
            target=_worker_loop, args=(run_worker, threading.Event()),
            name="hunter-scheduled-poller", daemon=True
        )
        thread.start()
        _started = True
    print("[scheduled] durable worker started", flush=True)
    return True

