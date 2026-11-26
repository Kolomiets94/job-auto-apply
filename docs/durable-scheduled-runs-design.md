# Durable scheduled-run queue

## Implemented in this branch

- `scheduled_tasks.py` creates a dedicated `hunter_run_tasks` table.
- Enqueue is idempotent by task ID.
- Claims are atomic: PostgreSQL uses `FOR UPDATE SKIP LOCKED`; local SQLite uses `BEGIN IMMEDIATE`.
- Tasks have bounded attempts, worker ownership, lease expiry, completion/failure recording, and lease renewal.
- `scheduled_worker.py` is a supervised polling process. It refuses to start or execute tasks unless `DRY_RUN=1`.
- `/run/scheduled` has an opt-in queue mode controlled by `HUNTER_SCHEDULED_QUEUE_ENABLED=1`. The default remains the existing behavior until a separate worker is deployed.

## Required deployment step before enabling queue mode

Deploy a separate Render Background Worker from this repository with start command:

```bash
python scheduled_worker.py
```

It must use the same `DATABASE_URL` as the web service and have `DRY_RUN=1`. Only after the worker is healthy should the web service receive `HUNTER_SCHEDULED_QUEUE_ENABLED=1`. Do not enable that flag before the worker is deployed, or scheduled runs will queue without being processed.

## Safety and rollout

- The branch does not alter production environment variables, Render services, or the database.
- No scheduler endpoint is invoked by tests or development work.
- The worker fails closed unless `DRY_RUN=1`; application approval gates remain unchanged.
- The queue is at-least-once execution: a worker crash after side effects but before completion can lead to a retry. Existing draft-only behavior makes this safer, but before any live-application mode is considered, every external side effect must have its own idempotency key and explicit approval review.
- Configure a worker process monitor/restart policy in Render. The database lease recovers abandoned tasks when a worker is available again; it does not itself provision or supervise the worker.
