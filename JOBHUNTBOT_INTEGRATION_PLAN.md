# JobHuntBot integration plan

Status: audit and preparation only. This document does not enable live applications, email sending, paid services, GitHub Actions, or a production deploy.

## Target
Extend the existing Flask + worker + queue_store application in place. Keep the current Render service and the `render-playwright-migration` branch. Do not modify `main`.

Search geography: Russia-based candidate; Russian vacancies and international roles only when the employer or vacancy evidence confirms applications/work from Russia are eligible.

## Audit findings

### Existing capabilities to preserve
- Multi-source collectors and bounded concurrent collection in `worker.py`.
- Resume text loading and deterministic matching in `job_matcher.py`.
- Ranking and role ordering in `profit_ranker.py`.
- SQLite/PostgreSQL-backed lead queue and deduplication in `queue_store.py`.
- Proposal drafts in `proposal_writer.py`.
- Telegram notifications and protected Telegram test form.
- Dry-run gates and explicit feature flags for browser/email/freelance submission.
- Existing tests for collectors, matching, deduplication, dispatch, notifications and scheduling.

### Gaps versus JobHuntBot
- The queue stores a compact state and payload, but does not yet expose a complete candidate-owned application history, blocker queue, follow-up calendar, or structured outcome evidence.
- Candidate facts and resume routing are mostly environment/file text, not a validated profile with explicit unknown values.
- No mobile-friendly, authenticated dashboard currently presents the full funnel and lets the candidate review blockers/outcomes.
- International eligibility must be evidence-based. A generic Worldwide/Remote label must not be treated as proof that work from Russia is allowed.
- Existing legacy config contains hard-coded city defaults and should be checked for active call sites before it is treated as authoritative.
- The old rules file contained a dated broad auto-submit authorization. It has been replaced with current per-action consent boundaries; no submission authorization is assumed.

## Design decisions

1. Keep Flask, the existing worker, and the current database abstraction. Do not transplant JobHuntBot's local Node/CSV dashboard as a second source of truth.
2. Adapt JobHuntBot's concepts, not its local runtime:
   - candidate profile with confirmed facts and explicit unknowns;
   - role-specific resume routing;
   - screening rules with evidence and eligibility status;
   - application progress checkpoints;
   - blocker queue and follow-up events;
   - evidence-backed outcome tracking.
3. Extend the existing database with additive migrations. Preserve old lead records and existing states; provide explicit state mapping rather than silently renaming states.
4. Add read-only dashboard/API first. Mutations should be narrow, authenticated, validated, and auditable.
5. Keep personal data, resumes, contact details, browser state, tokens and application history out of public Git. Store private profile/resume content only in private Render environment/storage or the private database, with access controls.
6. Treat application submission as a separate capability. Keep `DRY_RUN=1`, `AUTO_BROWSER_APPLY=0`, `AUTO_SEND_EMAIL=0`, and `AUTO_FREELANCE_APPLY=0`.

## Phased implementation

### Phase 1 — rules and data model
- Completed: update `JOB_FUNNEL_RULES.md` to Russia-based eligibility and current consent boundaries.
- Add a versioned candidate profile schema (no personal values populated without user confirmation).
- Add resume-routing metadata for Frontend React/TypeScript and HTML/CSS layout.
- Add application event/evidence records and blocker/follow-up tables.
- Add migrations and backward-compatibility tests.

### Phase 2 — evidence-aware screening
- Normalize country/region/remote-eligibility evidence from collectors.
- Distinguish `eligible_from_russia`, `ineligible_from_russia`, and `eligibility_unclear`.
- Preserve salary amount, currency, period, source and unknown status; avoid comparing annual and monthly figures without normalization.
- Add tests for worldwide wording, country restrictions, sponsorship ambiguity, salary_unknown and duplicate postings.

### Phase 3 — mobile dashboard
- Serve a responsive dashboard from the existing Flask service.
- Show funnel counts, vacancy cards, source link, salary/eligibility evidence, match score, resume recommendation, blockers, next action and follow-up date.
- Allow only safe review actions initially: shortlist, skip with reason, mark interview/offer/rejection when user reports it, and add follow-up reminders.
- Do not expose private candidate data in public endpoints.

### Phase 4 — Telegram workflow
- Send concise new-match and blocker notifications.
- Link back to the authenticated dashboard.
- Add explicit review/approval handoff. A Telegram button must not submit an application unless a separate approval action is implemented and verified.

### Phase 5 — verification and deployment
- Run unit and regression tests locally/CI-free.
- Inspect branch diff and confirm no secrets or personal data are included.
- Deploy only after a safe review; keep dry-run and send flags disabled.
- Verify dashboard read-only behavior and Telegram notifications without sending real applications.

## Acceptance criteria
- Existing lead queue and deduplication behavior remain intact.
- A vacancy cannot be called eligible from Russia without explicit supporting evidence.
- Unknown salary and unknown work authorization remain visibly unknown.
- Each application status change has timestamp, source, and evidence.
- Dashboard works on a phone and does not leak candidate details.
- No email, browser application, paid bid, or final submission occurs during search/draft mode.
