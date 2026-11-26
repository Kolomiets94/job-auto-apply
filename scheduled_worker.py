"""Supervised polling process for persistent scheduled hunter runs.

Run as a separate Render Background Worker, not inside Gunicorn.
"""
import os
import signal
import socket
import threading
import time
import uuid

from scheduled_tasks import (
    claim_scheduled_task,
    finish_scheduled_task,
    fail_scheduled_task,
    renew_scheduled_task_lease,
)

POLL_SECONDS = max(2, int(os.getenv("HUNTER_TASK_POLL_SECONDS", "15")))
LEASE_SECONDS = max(60, int(os.getenv("HUNTER_TASK_LEASE_SECONDS", "900")))
STOP = threading.Event()


def _heartbeat(task_id, worker_id, lost_lease, heartbeat_stop):
    interval = max(10, LEASE_SECONDS // 3)
    while not heartbeat_stop.wait(interval):
        try:
            if not renew_scheduled_task_lease(task_id, worker_id, LEASE_SECONDS):
                lost_lease.set()
                return
        except Exception:
            # A transient DB failure must not silently permit ownership assumptions.
            lost_lease.set()
            return


def process_one(worker_id, run_worker):
    task = claim_scheduled_task(worker_id=worker_id, lease_seconds=LEASE_SECONDS)
    if not task:
        return False

    lost_lease = threading.Event()
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(task["id"], worker_id, lost_lease, heartbeat_stop), daemon=True
    )
    heartbeat.start()
    try:
        # Scheduled runs are intentionally draft-only. Fail closed if misconfigured.
        if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
            raise RuntimeError("scheduled worker requires DRY_RUN=1")
        run_worker()
        if not lost_lease.is_set():
            finish_scheduled_task(task["id"], worker_id)
    except Exception as exc:
        if not lost_lease.is_set():
            fail_scheduled_task(task["id"], worker_id, exc)
        raise
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2)
    return True


def main():
    if os.getenv("DRY_RUN", "").strip().lower() not in ("1", "true", "yes"):
        raise SystemExit("Refusing to start scheduled worker unless DRY_RUN=1")
    worker_id = os.getenv("HUNTER_WORKER_ID") or (
        f"{socket.gethostname()}:{uuid.uuid4().hex[:12]}"
    )
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    from worker import run as run_worker

    while not STOP.is_set():
        try:
            worked = process_one(worker_id, run_worker)
            if not worked:
                STOP.wait(POLL_SECONDS)
        except Exception:
            # The task is persisted with retry/terminal state; keep the supervisor alive.
            print("[scheduled-worker] task failed; will poll again", flush=True)
            STOP.wait(POLL_SECONDS)


if __name__ == "__main__":
    main()
