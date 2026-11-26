"""Durable PostgreSQL/SQLite queue for draft-only scheduled hunter runs.

The web endpoint can enqueue a task; a separately supervised worker claims it.
A lease makes abandoned RUNNING tasks eligible for another worker after a crash.
"""
import json
import os
import socket
import uuid
from datetime import datetime, timezone, timedelta

from queue_store import _db

MAX_ATTEMPTS = 5


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat()


def ensure_scheduled_task_table():
    with _db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS hunter_run_tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                lease_until TEXT,
                worker_id TEXT,
                last_error TEXT
            )
        """)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS hunter_run_tasks_claim_idx "
            "ON hunter_run_tasks(status, lease_until, created_at)"
        )


def enqueue_scheduled_task(task_id, payload=None):
    """Idempotently persist a task. Returns True only for a newly inserted task."""
    if not task_id or len(str(task_id)) > 200:
        raise ValueError("invalid task id")
    ensure_scheduled_task_table()
    now = _iso(_now())
    encoded = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
    with _db() as connection:
        result = connection.execute(
            """INSERT INTO hunter_run_tasks
               (id,status,payload,attempts,created_at,updated_at)
               VALUES(?, 'pending', ?, 0, ?, ?)
               ON CONFLICT (id) DO NOTHING""",
            (str(task_id), encoded, now, now),
        )
        return result.rowcount == 1


def claim_scheduled_task(worker_id=None, lease_seconds=900):
    """Atomically claim one pending or expired task; concurrent workers cannot share it."""
    ensure_scheduled_task_table()
    worker_id = worker_id or f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
    now = _now()
    now_text = _iso(now)
    lease_text = _iso(now + timedelta(seconds=max(30, int(lease_seconds))))
    if os.getenv("DATABASE_URL", "").strip():
        with _db() as connection:
            row = connection.execute(
                """WITH candidate AS (
                       SELECT id FROM hunter_run_tasks
                       WHERE attempts < ? AND (
                           status='pending' OR
                           (status='running' AND lease_until IS NOT NULL AND lease_until <= ?)
                       )
                       ORDER BY created_at ASC
                       LIMIT 1
                       FOR UPDATE SKIP LOCKED
                   )
                   UPDATE hunter_run_tasks
                   SET status='running', attempts=attempts+1, updated_at=?,
                       lease_until=?, worker_id=?
                   WHERE id=(SELECT id FROM candidate)
                   RETURNING id,payload,attempts""",
                (MAX_ATTEMPTS, now_text, now_text, lease_text, worker_id),
            ).fetchone()
    else:
        with _db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT id,payload,attempts FROM hunter_run_tasks
                   WHERE attempts < ? AND (
                       status='pending' OR
                       (status='running' AND lease_until IS NOT NULL AND lease_until <= ?)
                   )
                   ORDER BY created_at ASC LIMIT 1""",
                (MAX_ATTEMPTS, now_text),
            ).fetchone()
            if row:
                connection.execute(
                    """UPDATE hunter_run_tasks SET status='running',
                       attempts=attempts+1,updated_at=?,lease_until=?,worker_id=?
                       WHERE id=?""",
                    (now_text, lease_text, worker_id, row[0]),
                )
                row = (row[0], row[1], row[2] + 1)
    if not row:
        return None
    try:
        payload = json.loads(row[1])
    except (TypeError, ValueError):
        payload = {}
    return {"id": row[0], "payload": payload, "attempts": row[2], "worker_id": worker_id}


def finish_scheduled_task(task_id, worker_id):
    """Complete only a task still leased by this worker."""
    now = _iso(_now())
    with _db() as connection:
        result = connection.execute(
            """UPDATE hunter_run_tasks SET status='completed',updated_at=?,
               lease_until=NULL,worker_id=NULL,last_error=NULL
               WHERE id=? AND status='running' AND worker_id=?""",
            (now, task_id, worker_id),
        )
    return result.rowcount == 1


def fail_scheduled_task(task_id, worker_id, error):
    """Return a failed attempt to pending, or mark terminal after MAX_ATTEMPTS."""
    now = _iso(_now())
    safe_error = str(error or "unknown error").replace("\\n", " ")[:500]
    with _db() as connection:
        result = connection.execute(
            """UPDATE hunter_run_tasks
               SET status=CASE WHEN attempts >= ? THEN 'failed' ELSE 'pending' END,
                   updated_at=?,lease_until=NULL,worker_id=NULL,last_error=?
               WHERE id=? AND status='running' AND worker_id=?""",
            (MAX_ATTEMPTS, now, safe_error, task_id, worker_id),
        )
    return result.rowcount == 1


def scheduled_task_status(task_id):
    ensure_scheduled_task_table()
    with _db() as connection:
        row = connection.execute(
            """SELECT id,status,attempts,created_at,updated_at,lease_until,last_error
               FROM hunter_run_tasks WHERE id=?""",
            (task_id,),
        ).fetchone()
    if not row:
        return None
    return dict(zip(
        ("id", "status", "attempts", "created_at", "updated_at", "lease_until", "last_error"),
        row,
    ))


def renew_scheduled_task_lease(task_id, worker_id, lease_seconds=900):
    """Extend a live lease; a worker that lost ownership cannot renew it."""
    now = _now()
    with _db() as connection:
        result = connection.execute(
            """UPDATE hunter_run_tasks SET updated_at=?,lease_until=?
               WHERE id=? AND status='running' AND worker_id=?""",
            (_iso(now), _iso(now + timedelta(seconds=max(30, int(lease_seconds)))),
             task_id, worker_id),
        )
    return result.rowcount == 1


def scheduled_task_summary(limit=10):
    """Read-only aggregate and recent task metadata; never returns payloads or worker IDs."""
    limit = max(1, min(int(limit), 50))
    with _db() as connection:
        counts = connection.execute(
            "SELECT status,COUNT(*) FROM hunter_run_tasks GROUP BY status"
        ).fetchall()
        recent = connection.execute(
            """SELECT id,status,attempts,created_at,updated_at,lease_until,last_error
               FROM hunter_run_tasks ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    status_counts = {str(status): int(count) for status, count in counts}
    tasks = [
        {
            "id": row[0],
            "status": row[1],
            "attempts": int(row[2]),
            "created_at": row[3],
            "updated_at": row[4],
            "lease_until": row[5],
            "last_error": row[6],
        }
        for row in recent
    ]
    return {
        "total": sum(status_counts.values()),
        "status_counts": status_counts,
        "recent_tasks": tasks,
    }
