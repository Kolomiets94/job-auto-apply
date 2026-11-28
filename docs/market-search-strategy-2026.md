# Selective job-search strategy for the 2026 market

## Purpose

The reported contraction in vacancies and increase in candidate supply calls for better targeting, not weaker eligibility checks or inflated match scores. This document defines a conservative strategy for the JobAutoApply pipeline.

## Search coverage

Keep the existing priority order:
1. React / Frontend Developer
2. JavaScript / TypeScript Developer when the actual duties are frontend-focused
3. Web Developer / UI Developer when the vacancy describes browser-based interface work
4. HTML/CSS layout and implementation roles
5. QA only as an explicitly secondary track when the vacancy is suitable for the verified profile

Search aliases are discovery hints, not proof of fit. Every result must pass the existing enrichment, location, work-authorization, seniority, salary, and profile-evidence checks.

## Classification

Each vacancy should be described in one of these review groups:

- **Ready to review** — evidence in the candidate profile supports the core duties and hard conditions are compatible.
- **Adjacent / stretch** — role is related, but one or more material skills or experience requirements need human assessment.
- **Hard constraint mismatch** — explicit residence, work-authorization, mandatory onsite/hybrid location, or other non-negotiable condition conflicts with the candidate's stated constraints.
- **Insufficient evidence** — source text or candidate evidence is too incomplete to make a reliable determination.

A high ATS text score must never override a hard-constraint mismatch. An ATS score is a heuristic text comparison, not an employer ATS result or probability of interview.

## Freshness and salary

- Prefer recently published vacancies when comparing otherwise equivalent candidates.
- Preserve the original publication timestamp and source; do not infer freshness when it is missing.
- Treat salary as a separate dimension: in-range explicit salary, below-range explicit salary, and undisclosed/ambiguous salary must remain distinguishable.
- Do not silently discard undisclosed salary if the existing policy permits manual review.
- Do not invent salary ranges or adjust thresholds from a single market article.

## Evidence and candidate claims

- Use only verified resume and project evidence in match explanations and application drafts.
- Distinguish personal projects from commercial employment.
- Never add AI, MLOps, DevSecOps, infrastructure, or other skills solely because they appear in market commentary or a vacancy.
- Recommend learning priorities only when a skill recurs across collected vacancies and is relevant to the target role; label it as a development suggestion, not an existing competency.

## Reporting

Telegram summaries should make the following visible where data exists:
- counts by the four review groups;
- top hard-constraint rejection reasons;
- publication freshness distribution, with an explicit unknown bucket;
- salary visibility (explicit / undisclosed / rejected by policy);
- recurring skill gaps, clearly separated from verified skills.

## Rollout and safety

This is a policy specification, not authorization to change production behavior. Implement future runtime changes in small PRs with deterministic tests. Preserve free-tier compatibility, `DRY_RUN=1`, human review, and all existing location/work-authorization constraints. Never send applications, emails, bids, or recruiter messages as part of search or diagnostics.
