# Durable scheduled-run design

## Current failure mode

The application already persists discovered vacancies in the `leads` table, but that table is a vacancy queue, not a scheduler task queue. The `hunter_scheduled_runs` table currently records only a unique run ID, start/completion timestamps, and an outcome. The scheduled endpoint claims a row and then starts `run_worker()` in a daemon thread inside the Flask/Gunicorn process. A process restart can terminate that thread while the database row remains claimed and incomplete.

## Proposed staged implementation

1. Introduce a dedicated `hunter_run_tasks` table with a stable task ID, status (`pending`, `running`, `completed`, `failed`), attempt count, created/updated timestamps, lease expiry, and a bounded error summary.
2. Make `/run/scheduled` persist a task before returning HTTP 202. Preserve the existing GitHub OIDC validation, schedule/manual idempotency keys, and mandatory `DRY_RUN=1` gate.
3. Claim tasks atomically in PostgreSQL using row locking / `SKIP LOCKED`; keep a SQLite-compatible implementation for local tests. A lease allows a later worker to reclaim tasks abandoned by a process crash.
4. Keep execution idempotent and ensure a task retry cannot bypass existing application approval and dry-run checks.
5. Add read-only task status diagnostics that expose counts and timestamps, never secrets or vacancy personal data.
6. Test duplicate triggers, concurrent claims, expired-lease recovery, failure recording, and dry-run enforcement.

## Safety and rollout

- Do not change `DRY_RUN`, `AUTO_APPLY_APPROVED`, application channel settings, or credentials.
- Do not invoke live `/run` or `/run/scheduled` endpoints during development.
- Do not merge or deploy this branch until migration behavior, concurrency semantics, and tests are reviewed.
- A persistent task queue improves recovery on the next worker poll/trigger; full continuous processing still requires a separately managed worker process or an explicitly supervised worker loop. Do not claim daemon-thread execution is durable by itself.
