# Durable scheduled-run queue

## Implemented in this branch

- `scheduled_tasks.py` creates a dedicated `hunter_run_tasks` table.
- Enqueue is idempotent by task ID.
- Claims are atomic: PostgreSQL uses `FOR UPDATE SKIP LOCKED`; local SQLite uses `BEGIN IMMEDIATE`.
- Tasks have bounded attempts, worker ownership, lease expiry, completion/failure recording, and lease renewal.
- `scheduled_worker.py` is a supervised polling process. It refuses to start or execute tasks unless `DRY_RUN=1`.
- `/run/scheduled` has an opt-in queue mode controlled by `HUNTER_SCHEDULED_QUEUE_ENABLED=1`. The default remains the existing behavior until a separate worker is deployed.

## Free-tier deployment model

A separate Render Background Worker is not required. Render does not offer free Background Worker or Cron Job instances; those service types are billed separately. The existing free web service consumes one queued task in a daemon thread after each authenticated GitHub Actions trigger.

Set `HUNTER_SCHEDULED_QUEUE_ENABLED=1` on the existing web service only after this branch is deployed and verified. Keep `DRY_RUN=1` and the existing `DATABASE_URL`. No new Render service or paid plan is needed.

This is a best-effort free-tier consumer, not an always-on worker. Free web services can spin down after inactivity or restart at any time. If a task is interrupted, its lease expires and a later scheduled trigger can reclaim it. A task may therefore wait until the next trigger; do not describe this as continuous background processing.

## Safety and rollout

- The branch does not alter production environment variables, Render services, or the database.
- No scheduler endpoint is invoked by tests or development work.
- The worker fails closed unless `DRY_RUN=1`; application approval gates remain unchanged.
- The queue is at-least-once execution: a worker crash after side effects but before completion can lead to a retry. Existing draft-only behavior makes this safer, but before any live-application mode is considered, every external side effect must have its own idempotency key and explicit approval review.
- The free web process is not continuously supervised. The database lease recovers abandoned tasks only when a later GitHub Actions trigger wakes the web service and attempts a claim.
