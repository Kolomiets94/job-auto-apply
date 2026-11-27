# Agentic pipeline architecture

## Goal

Evolve JobAutoApply from a large one-pass worker into a controlled, observable pipeline. The goal is not to add an autonomous agent that can do anything. It is to make each existing engineering stage explicit, independently testable, and auditable while keeping the current free-tier deployment and draft-only safety model.

This document is an architecture plan. It does not change runtime behavior, environment variables, scheduler settings, or application-dispatch permissions.

## Design principles

1. **Deterministic gates before generative assistance.** Geography, work authorization, role, salary, seniority, required skills, duplicate detection, and application policy remain explicit code rules. An LLM must never override a blocked or unknown gate.
2. **Evidence before claims.** Candidate skills and project facts come only from the verified resume/profile and checked project evidence. Vacancy text is not candidate evidence. Unknown facts stay unknown.
3. **Small stages with explicit contracts.** Each stage accepts normalized input and returns structured output, diagnostics, and a status. Stages must not silently mutate unrelated data.
4. **Validate every handoff.** Schema validation, invariants, unit tests, and regression fixtures protect stage boundaries. A downstream stage must reject malformed or incomplete upstream output.
5. **Human approval for consequential actions.** Discovery, analysis, ranking, and draft generation may be automated. Sending an application, email, bid, or recruiter message remains separately gated and is out of scope for this architecture phase.
6. **Free-tier first.** No paid workers, paid model APIs, paid data sources, or additional always-on services. The existing GitHub Actions + free Render + PostgreSQL arrangement remains.
7. **Observable, privacy-safe execution.** Record counts, durations, stage statuses, and stable reason codes. Do not log full resumes, cover letters, credentials, private messages, or unnecessary personal data.

## Proposed pipeline

| Stage | Responsibility | Existing implementation / likely boundary |
|---|---|---|
| 1. Collect | Fetch public vacancies and projects from configured sources | `job_sources.py`, `main.py`, `freelance_sources.py` |
| 2. Normalize & deduplicate | Convert source cards into one canonical lead shape; deduplicate by canonical URL | `worker.py` collection helpers and `_lead_key` |
| 3. Enrich | Read full vacancy text where available; preserve source and retrieval status | Existing enrichment helpers called from `worker.py` |
| 4. Assess conditions | Determine remote/hybrid, Russia eligibility, pay, and other hard constraints as confirmed / blocked / unknown | `ats_conditions.py` |
| 5. Evaluate profile fit | Compare vacancy with verified resume/profile; report matches and gaps without inventing skills | `ats_evaluator.py`, `resume_parser.py` |
| 6. Rank & explain | Apply deterministic role, geography, salary, seniority, skill, and policy rules; emit stable reason codes | `profit_ranker.py`, `job_matcher.py` |
| 7. Build evidence packet | Select only verified candidate facts and relevant checked projects for a particular role | `proposal_writer.py` and evidence policy |
| 8. Draft | Generate a concise, evidence-only cover letter or outreach draft | `proposal_writer.py`, `direct_outreach.py` |
| 9. Review & persist | Save drafts, flag uncertain cases, and require human review where needed | `queue_store.py`, manual-review reporting |
| 10. Notify | Send aggregate results and shortlists to Telegram | `telegram_notifier.py`, `notification_rules.py` |

The first implementation should extract and test boundaries around the current deterministic pipeline, not replace it wholesale with an LLM agent.

## Stage contract

A future stage result should use a small common shape:

- `stage`: stable stage identifier;
- `status`: `ok`, `partial`, `blocked`, or `error`;
- `input_count` and `output_count`;
- `reason_counts`: stable machine-readable reason codes and counts;
- `duration_ms`;
- `items`: stage-specific output, not copied into logs;
- `warnings`: sanitized, non-sensitive diagnostic codes.

Stage functions should be as close to pure functions as practical. Network collection, database persistence, and Telegram delivery remain explicit side-effect boundaries. A failed optional source should produce a partial collection result rather than erase successful results from other sources.

## Agent boundaries

An LLM or agent may eventually assist with:
- extracting structured facts from a vacancy description;
- summarizing a long vacancy with citations to its source text;
- explaining why a deterministic rule matched or rejected a lead;
- selecting relevant facts from an already verified evidence packet;
- drafting language from those facts.

An LLM or agent must not:
- decide that an unknown work-authorization or location condition is confirmed;
- invent or infer candidate skills, employment history, metrics, or achievements;
- relax hard filters, salary limits, geography, or role scope;
- alter approval flags, scheduler configuration, or secrets;
- send applications, emails, bids, or recruiter messages;
- treat its own generated text as evidence.

Every model-assisted output must retain source references or evidence IDs for factual claims and pass deterministic validation before persistence or display.

## Recommended implementation sequence

### Phase 1 — observability and contracts

- Introduce a shared stage-result structure without changing business rules.
- Add stage-level counts, duration, and stable rejection reasons to the run report.
- Keep source-specific exceptions isolated and distinguish `partial` from `error`.
- Add tests for empty input, partial source failure, malformed stage output, and reason-code accounting.

### Phase 2 — extract deterministic stages

- Move normalization/deduplication, condition assessment, ranking, and evidence selection behind narrow functions.
- Preserve existing ordering and filtering behavior with golden regression fixtures.
- Compare old and refactored outputs on fixed fixtures before enabling the refactored path.

### Phase 3 — evidence packets and review

- Build a versioned candidate evidence packet from verified resume/profile and checked repositories.
- Give each fact a source, verification status, and scope (personal, educational, team, commercial).
- Require every draft claim to map to one or more evidence IDs.
- Keep unknown or unsupported claims out of generated drafts.

### Phase 4 — optional model assistance

- Only after Phases 1–3 are stable, consider a model-assisted extraction/explanation adapter.
- Use a provider interface so deterministic operation remains available when no model is configured.
- Require structured output, bounded input, explicit source references, and deterministic post-validation.
- Do not add a paid dependency or API requirement; default behavior must continue to work without a model.

### Phase 5 — supervised execution

- Treat each scheduled run as a durable, idempotent job with observable stage states.
- Preserve the current free-tier limitation: a free Render web process can sleep or restart, so queue recovery is best-effort on a later GitHub Actions trigger, not continuous processing.
- Do not claim a run completed merely because the scheduler endpoint returned HTTP 202.
- Keep scheduled execution draft-only and require a separate explicit authorization process for any future live mode.

## Acceptance criteria

- Existing filters, role priorities, salary limits, geographic rules, deduplication, and draft content remain unchanged during the refactor.
- A source failure cannot silently discard results from other sources.
- Every rejection/hold is attributable to a stable reason code.
- Every generated candidate claim can be traced to verified evidence.
- Tests cover stage contracts and preserve current behavior on representative fixtures.
- No new paid service, model API, Render service, or secret is required.
- `DRY_RUN=1` remains mandatory for scheduled worker execution; no application or outreach is sent by this work.
