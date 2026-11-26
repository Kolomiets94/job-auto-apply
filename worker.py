"""Unified one-pass job + freelance hunter worker."""

import os
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from job_sources import JOB_COLLECTORS

from main import QUERIES, HHAccessUnavailable, hh_search, hh_search_hybrid, remoteok
from freelance_sources import (
    collect_freelance, collect_peopleperhour, collect_prolinker,
    collect_weblancer, collect_freelancer_com,
)
from freelancehunt_adapter import collect_freelancehunt
from job_matcher import JobMatcher
from ats_evaluator import review_lead, build_market_report, build_filter_report
from ats_conditions import assess_job_conditions
from profit_ranker import rank_leads, rank_lead, FREELANCE_SOURCES, ROLE_PRIORITY, _role_category, _work_mode
from proposal_writer import make_proposal
from application_dispatcher import dispatch
from application_approval import live_applications_approved
from queue_store import enqueue, enqueue_many, set_state, submitted_today, submitted_this_week, was_submitted, queued_leads, save_outreach_drafts, list_outreach, build_outcome_feedback_report
from notification_rules import format_notification, should_notify
from telegram_notifier import send_message, send_notification
from publication_filter import is_new_publication
from direct_outreach import build_outreach_drafts
from resume_parser import extract_resume_text, ResumeParseError

DEFAULT_RESUME_TEXT = ""  # Never invent skills or project history when no verified resume is configured.


def load_resume_text():
    # RESUME_TEXT is the explicit inline-text setting. RESUME is a backwards-
    # compatible alias and may contain either resume text or an existing file path.
    text = os.getenv("RESUME_TEXT", "").strip()
    if text:
        return text

    resume_value = os.getenv("RESUME", "").strip()
    if resume_value:
        # Resume text is commonly multiline and can exceed the OS filename
        # limit. Only probe short, single-line values as possible file paths.
        if "\n" not in resume_value and "\r" not in resume_value and len(resume_value) <= 240:
            try:
                candidate = Path(resume_value).expanduser()
                if candidate.is_file():
                    return extract_resume_text(str(candidate))
            except (OSError, ResumeParseError) as exc:
                print(f"[resume] RESUME file could not be read; live applications remain blocked: {type(exc).__name__}", flush=True)
                return DEFAULT_RESUME_TEXT
        # Multiline/long values are inline resume text, not filesystem paths.
        return resume_value

    path = os.getenv("RESUME_FILE", "resume/profile.txt")
    try:
        return extract_resume_text(path)
    except FileNotFoundError:
        return DEFAULT_RESUME_TEXT
    except ResumeParseError as exc:
        print(f"[resume] parsing failed; live applications remain blocked: {exc}", flush=True)
        return DEFAULT_RESUME_TEXT


COLLECTION_ERRORS = []
COLLECTION_RAW_COUNT = 0


def _lead_key(lead):
    """Canonicalize HH URLs so the same vacancy found by several queries is processed once."""
    url = str(lead.get("url") or "")
    match = __import__("re").search(r"https?://(?:www\.)?hh\.ru/vacancy/(\d+)", url)
    if match:
        return f"hh:{match.group(1)}"
    if url:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(url)
        query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_") and k not in ("ref", "source")]
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))
    return str(lead)


def record_collection_error(source, exc):
    status = getattr(getattr(exc, "response", None), "status_code", None)
    reason = type(exc).__name__ + (f" HTTP {status}" if status else "")
    COLLECTION_ERRORS.append({"source": source, "reason": reason})
    print(f"[collector] {source}: {reason}", flush=True)


def _deduplicate_leads(leads):
    """Deduplicate normalized leads by their canonical source URL."""
    seen = set()
    unique = []
    for lead in leads:
        key = _lead_key(lead)
        if key in seen:
            continue
        seen.add(key)
        unique.append(lead)
    return unique


def collect_freelance_all():
    """Collect freelance projects only after employment vacancies fail the filters."""
    global COLLECTION_RAW_COUNT
    leads = []
    for source, collector in (
        ("freelance", collect_freelance),
        # PeoplePerHour and ProLinker do not expose a reliable publication
        # timestamp, so today's fail-closed filter would discard every card.
        ("freelancehunt", collect_freelancehunt),
        ("weblancer", collect_weblancer),
        ("freelancer_com", collect_freelancer_com),
    ):
        try:
            collected = collector()
            leads.extend(collected)
            print(f"[collector] {source}: {len(collected)} leads", flush=True)
        except Exception as exc:
            record_collection_error(source, exc)
    COLLECTION_RAW_COUNT += len(leads)
    return _deduplicate_leads(leads)


def collect_all():
    """Collect employment vacancies only; freelance discovery is a true fallback."""
    global COLLECTION_RAW_COUNT
    COLLECTION_ERRORS.clear()
    COLLECTION_RAW_COUNT = 0
    leads = []
    hh_available = True
    for tag, query in QUERIES:
        try:
            matches = hh_search(tag, query)
            print(f"[collector] hh {tag} / {query}: {len(matches)} leads", flush=True)
            leads += matches
        except Exception as exc:
            record_collection_error(f"hh:{tag}:{query}", exc)
            if isinstance(exc, HHAccessUnavailable):
                # Every remaining query uses the same unavailable channel.
                # Avoid repeating a blocked API request for each search term.
                hh_available = False
                break

    # Also collect HH hybrid vacancies in Yekaterinburg; the ranker rejects hybrid roles elsewhere.
    for tag, query in (QUERIES if hh_available else []):
        try:
            matches = hh_search_hybrid(tag, query)
            print(f"[collector] hh hybrid {tag} / {query}: {len(matches)} leads", flush=True)
            leads += matches
        except Exception as exc:
            record_collection_error(f"hh-hybrid:{tag}:{query}", exc)
            if isinstance(exc, HHAccessUnavailable):
                break

    try:
        leads += remoteok()
    except Exception as exc:
        record_collection_error("remoteok", exc)

    # Independent employment sources run concurrently with bounded request timeouts.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(collector): source for source, collector in JOB_COLLECTORS}
        for future in as_completed(futures):
            source = futures[future]
            try:
                collected = future.result()
                leads.extend(collected)
                print(f"[collector] {source}: {len(collected)} leads", flush=True)
            except Exception as exc:
                record_collection_error(source, exc)

    COLLECTION_RAW_COUNT = len(leads)
    return _deduplicate_leads(leads)


def apply_resume_matching(leads, resume_text=None):
    resume_text = load_resume_text() if resume_text is None else resume_text
    conditioned = [{**lead, **assess_job_conditions(lead)} for lead in leads]
    if not resume_text:
        return conditioned
    matcher = JobMatcher()
    return [review_lead(matcher.score_lead(lead, resume_text), resume_text) for lead in conditioned]


def is_freelance(lead):
    return str(lead.get("source") or "").lower() in FREELANCE_SOURCES


def _application_priority(lead):
    """Prefer channels the dispatcher can actually submit through.

    Unknown external forms stay visible for review, but cannot crowd out
    email, HH, Remote-job or configured Freelancehunt API applications.
    """
    if lead.get("paid_bid") is True:
        return 2
    if lead.get("apply_email") or str(lead.get("apply_url") or "").lower().startswith("mailto:"):
        return 0 if os.getenv("AUTO_SEND_EMAIL") == "1" and all(
            os.getenv(key) for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
        ) else 1
    source = str(lead.get("source") or "").lower()
    if source == "hh":
        return 0 if os.getenv("AUTO_BROWSER_APPLY") == "1" and os.getenv("HH_STORAGE_STATE_JSON") else 1
    if source == "remote_job_ru":
        return 0 if os.getenv("AUTO_BROWSER_APPLY") == "1" and all(
            os.getenv(key) for key in ("REMOTE_JOB_NAME", "REMOTE_JOB_PHONE")
        ) and (os.getenv("REMOTE_JOB_EMAIL") or os.getenv("SMTP_USER")) else 1
    if source == "freelancehunt" and lead.get("can_api_bid") and os.getenv("FREELANCEHUNT_TOKEN") and os.getenv("AUTO_FREELANCE_APPLY") == "1":
        return 0
    return 1


def prioritize_actionable_leads(ranked):
    """Try React first, then other frontend and layout employment leads."""
    def priority(lead):
        role = _role_category(lead)
        title = str(lead.get("title") or "").lower()
        react_first = 0 if role == "frontend" and "react" in title else 1
        channel = _application_priority(lead)
        placement_first = 0 if lead.get("opportunity_type") == "paid_placement" else 1
        return (
            1 if is_freelance(lead) else 0,
            placement_first,
            ROLE_PRIORITY.get(role, 99),
            react_first,
            channel,
            -lead.get("profit_score", 0),
        )

    return sorted(ranked, key=priority)


def select_primary_leads(ranked):
    """Use freelance only as a fallback when no eligible employment vacancy exists."""
    ordered = prioritize_actionable_leads(ranked)
    jobs = [lead for lead in ordered if not is_freelance(lead)]
    freelance = [lead for lead in ordered if is_freelance(lead)]
    return (jobs if jobs else freelance), jobs, freelance


def _suppress_telegram_message(_text):
    """Keep discovery alerts out of Telegram; the run summary is the sole message."""
    return {"status": "SKIPPED", "reason": "summary_only_mode"}


def deliver_notifications(notifications):
    # Retain notification counts for diagnostics, but never send per-vacancy alerts.
    return [
        {"title": item.get("title"), "status": "SKIPPED", "reason": "summary_only_mode"}
        for item in notifications
    ]


def _application_limit(name):
    """Zero or an unset limit means no application-count cap."""
    value = int(os.getenv(name, "0") or "0")
    return value if value > 0 else None


def _limit_label(value):
    return str(value) if value is not None else "без лимита"


def _browser_scope(lead):
    """Pause challenges per destination, keeping other application sites usable."""
    from urllib.parse import urlsplit
    if lead.get('apply_email') or str(lead.get('apply_url') or '').startswith('mailto:'):
        return None
    source = str(lead.get('source') or '').lower()
    apply_url = str(lead.get('apply_url') or '')
    try:
        host = urlsplit(apply_url).hostname
    except ValueError:
        host = None
    if source == 'hh' or host == 'hh.ru' or (host or '').endswith('.hh.ru'):
        return 'hh.ru'
    if source == 'remote_job_ru':
        return 'remote-job.ru'
    if host and apply_url.startswith('https://'):
        return host.lower()
    return None


def _uses_browser(lead):
    return _browser_scope(lead) is not None



def build_job_source_diagnostics(candidates, enriched, assessed):
    """Summarize the employment-vacancy funnel without exposing listing text or PII."""
    from collections import Counter, defaultdict

    by_source = defaultdict(lambda: {
        "candidate_count": 0,
        "enriched_count": 0,
        "unavailable_count": 0,
        "enrichment_errors": Counter(),
        "assessed_count": 0,
        "eligible_count": 0,
        "manual_review_count": 0,
        "manual_review_reasons": Counter(),
        "rejected_reasons": Counter(),
        "roles": Counter(),
    })
    for lead in candidates:
        source = str(lead.get("source") or "unknown")
        by_source[source]["candidate_count"] += 1
    for lead in enriched:
        source = str(lead.get("source") or "unknown")
        item = by_source[source]
        if lead.get("enriched"):
            item["enriched_count"] += 1
        if lead.get("unavailable"):
            item["unavailable_count"] += 1
        error = lead.get("enrichment_error")
        if error:
            item["enrichment_errors"][str(error)] += 1
    for lead in assessed:
        source = str(lead.get("source") or "unknown")
        item = by_source[source]
        item["assessed_count"] += 1
        item["roles"][_role_category(lead)] += 1
        ranked = rank_lead(lead)
        if ranked.get("eligible"):
            item["eligible_count"] += 1
        else:
            item["rejected_reasons"][str(ranked.get("rank_reason") or "unknown")] += 1
            if ranked.get("manual_review_required"):
                item["manual_review_count"] += 1
                item["manual_review_reasons"][str(ranked.get("manual_review_reason") or "unspecified")] += 1

    result = {}
    for source, item in sorted(by_source.items()):
        result[source] = {
            "candidate_count": item["candidate_count"],
            "enriched_count": item["enriched_count"],
            "unavailable_count": item["unavailable_count"],
            "enrichment_errors": dict(item["enrichment_errors"].most_common(5)),
            "assessed_count": item["assessed_count"],
            "eligible_count": item["eligible_count"],
            "manual_review_count": item["manual_review_count"],
            "manual_review_reasons": dict(item["manual_review_reasons"].most_common(5)),
            "rejected_reasons": dict(item["rejected_reasons"].most_common(8)),
            "roles": dict(item["roles"]),
        }
    return result


def build_manual_review_list(assessed, limit=10):
    """Return bounded, linkable borderline vacancies; never make them eligible."""
    items = []
    for lead in assessed:
        ranked = rank_lead(lead)
        if not ranked.get("manual_review_required"):
            continue
        url = str(lead.get("url") or "").strip()
        if not url:
            continue
        items.append({
            "title": str(lead.get("title") or "Вакансия")[:100],
            "source": str(lead.get("source") or "?")[:40],
            "url": url,
            "reason": str(ranked.get("manual_review_reason") or ranked.get("rank_reason") or "Требуется проверка")[:120],
            "ats_score": lead.get("ats_score"),
        })
    return items[:max(0, int(limit))]


def run(force_dry_run=False):
    from aggregator_origin import reset_origin_diagnostics, origin_diagnostics
    from entry_level import is_placement
    global COLLECTION_RAW_COUNT
    COLLECTION_RAW_COUNT = 0
    reset_origin_diagnostics()
    try:
        started = _suppress_telegram_message("Job Auto Apply: поиск вакансий и заказов запущен.")
    except Exception as exc:
        started = {"status": "FAILED", "reason": type(exc).__name__}
    print(f"[telegram] start notification: {started}", flush=True)
    from lead_enrichment import enrich_lead

    # First discover, enrich and rank employment vacancies only. Do not spend
    # requests on freelance marketplaces while any suitable job vacancy exists.
    fresh_jobs = [lead for lead in collect_all()
                  if not is_freelance(lead) and is_new_publication(lead)]
    enqueue_many(fresh_jobs)
    queued = queued_leads(limit=1000)
    merged_jobs = {_lead_key(lead): lead for lead in queued if not is_freelance(lead)}
    merged_jobs.update({_lead_key(lead): lead for lead in fresh_jobs})
    job_candidates = [lead for lead in merged_jobs.values() if is_new_publication(lead)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        enriched_jobs = list(pool.map(enrich_lead, job_candidates))
    enqueue_many(enriched_jobs)
    job_leads = apply_resume_matching([
        lead for lead in enriched_jobs
        if not lead.get("unavailable") and is_new_publication(lead)
    ])
    ranked_jobs = rank_leads(job_leads)
    # Salary-ambiguous leads are excluded from dispatch and shown for human review.
    salary_review_jobs = [
        item for item in (rank_lead(lead) for lead in job_leads)
        if item.get("eligible") and item.get("salary_review_required") and item.get("url")
    ]

    fresh_freelance = []
    freelance_candidates = []
    enriched_freelance = []
    freelance_leads = []
    ranked_freelance = []

    # Only when no employment vacancy survives all role, location, work-mode,
    # salary and experience filters do we search the freelance fallback.
    if not ranked_jobs:
        fresh_freelance = [
            lead for lead in collect_freelance_all() if is_new_publication(lead)
        ]
        enqueue_many(fresh_freelance)
        queued = queued_leads(limit=1000)
        merged_freelance = {
            _lead_key(lead): lead for lead in queued if is_freelance(lead)
        }
        merged_freelance.update({
            _lead_key(lead): lead for lead in fresh_freelance
        })
        freelance_candidates = [
            lead for lead in merged_freelance.values()
            if is_new_publication(lead)
        ]
        with ThreadPoolExecutor(max_workers=3) as pool:
            enriched_freelance = list(pool.map(enrich_lead, freelance_candidates))
        enqueue_many(enriched_freelance)
        freelance_leads = apply_resume_matching([
            lead for lead in enriched_freelance
            if not lead.get("unavailable") and is_new_publication(lead)
        ])
        ranked_freelance = rank_leads(freelance_leads)

    fresh = fresh_jobs + fresh_freelance
    candidates = job_candidates + freelance_candidates
    enriched = enriched_jobs + enriched_freelance
    leads = job_leads + freelance_leads
    ranked, ranked_jobs, ranked_freelance = select_primary_leads(
        ranked_jobs + ranked_freelance
    )
    freelance_held_back = bool(ranked_jobs and ranked_freelance)
    # Diagnose why collected Junior Frontend/layout leads never reach dispatch.
    from collections import Counter
    eligibility = {}
    for role in ("frontend", "layout", "qa"):
        relevant = [lead for lead in leads if not is_freelance(lead) and _role_category(lead) == role]
        role_ranked = [rank_lead(lead) for lead in relevant]
        rejected = Counter(
            str(item.get("rank_reason") or "unknown")
            for item in role_ranked if not item.get("eligible")
        )
        manual_review = Counter(
            str(item.get("manual_review_reason") or "unspecified")
            for item in role_ranked if item.get("manual_review_required")
        )
        eligibility[role] = {
            "found": len(relevant),
            "eligible": sum(_role_category(lead) == role for lead in ranked_jobs),
            "manual_review_count": sum(manual_review.values()),
            "manual_review_reasons": dict(manual_review.most_common(5)),
            "rejected_reasons": dict(rejected.most_common(8)),
        }
    print(f"[eligibility] {eligibility}", flush=True)
    job_source_diagnostics = build_job_source_diagnostics(
        job_candidates, enriched_jobs, job_leads
    )
    print(f"[job_source_diagnostics] {job_source_diagnostics}", flush=True)

    daily_limits = {
        "jobs_submitted": _application_limit("DAILY_JOB_LIMIT"),
        "freelance_submitted": _application_limit("DAILY_FREELANCE_LIMIT"),
    }
    daily_counts = {"jobs_submitted": submitted_today("jobs"),
                    "freelance_submitted": submitted_today("freelance")}
    daily_limit = (sum(daily_limits.values())
                   if all(v is not None for v in daily_limits.values()) else None)
    submitted_count = sum(daily_counts.values())
    # One shared daily quota across every job and freelance platform.
    # Count only confirmed SUBMITTED applications from the persistent queue.
    # One non-configurable-by-platform shared cap; default and workflow setting are both 10.
    total_daily_limit = max(1, int(os.getenv("DAILY_TOTAL_LIMIT", "10") or "10"))
    weekly_total_limit = _application_limit("WEEKLY_TOTAL_LIMIT")
    weekly_submitted_count = submitted_this_week()
    total_hourly_limit = _application_limit("HOURLY_TOTAL_LIMIT")
    # Real submissions require a separate, explicit user approval.
    # Until AUTO_APPLY_APPROVED=1 is configured, always remain in draft mode.
    dry_run = (force_dry_run
               or os.getenv("DRY_RUN", "0").strip().lower() in ("1", "true", "yes")
               or not live_applications_approved())
    job_limit = _application_limit("HOURLY_JOB_LIMIT")
    freelance_limit = _application_limit("HOURLY_FREELANCE_LIMIT")

    source_counts = {name: 0 for name, _ in JOB_COLLECTORS}
    for lead in leads:
        source = str(lead.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1

    stats = {
        "freelance_found": sum(is_freelance(lead) for lead in leads),
        "freelance_ranked": len(ranked_freelance),
        "freelance_held_back": len(ranked_freelance) if freelance_held_back else 0,
        "frontend_found": sum(_role_category(lead) == "frontend" and not is_freelance(lead) for lead in leads),
        "layout_found": sum(_role_category(lead) == "layout" and not is_freelance(lead) for lead in leads),
        "qa_found": sum(_role_category(lead) == "qa" and not is_freelance(lead) for lead in leads),
        "source_counts": source_counts,
        "eligibility_diagnostics": eligibility,
        "job_source_diagnostics": job_source_diagnostics,
        "collection_errors": list(COLLECTION_ERRORS),
        "resume_configured": bool(load_resume_text()),
        "found": len(leads),
        "raw_found": COLLECTION_RAW_COUNT or len(fresh),
        "fresh_unique": len(fresh),
        "unique_checked": len(candidates),
        "fresh_found": len(fresh),
        "backlog_rechecked": len(candidates),
        "descriptions_enriched": sum(bool(lead.get("enriched")) for lead in enriched),
        "unavailable_skipped": sum(bool(lead.get("unavailable")) for lead in enriched),
        # Keep the legacy combined count while exposing the two channels
        # separately so freelance fallback cannot be mistaken for job vacancies.
        "ranked": len(ranked),
        "jobs_ranked": len(ranked_jobs),
        "primary_ranked": len(ranked),
        "submitted": 0,
        "drafted": 0,
        "submitted_by_role": {"frontend": 0, "layout": 0, "qa": 0, "freelance": 0},
        "jobs_submitted": 0,
        "freelance_submitted": 0,
        "shortlisted": 0,
        "needs_confirmation": 0,
        "skipped": 0,
        "failed": 0,
        "needs_human": 0,
        "duplicate_skipped": 0,
        "daily_limit_skipped": 0,
        "hourly_limit_skipped": 0,
        "browser_challenge_paused": 0,
        "paused_browser_hosts": [],
        "email_submitted_after_browser_pause": 0,
        "paid_placements_ranked": sum(is_placement(lead.get("title")) and not is_freelance(lead) for lead in ranked_jobs),
        "salary_manual_review": len(salary_review_jobs),
    }
    results = []
    notifications = []
    browser_challenge_streak = {}
    browser_pause_active = False
    challenge_reasons = {'remote_job_turnstile_required', 'security_challenge',
                         'aggregator_security_challenge'}

    for lead in ranked:
        freelance = is_freelance(lead)
        if lead.get("salary_review_required"):
            results.append({
                "title": lead.get("title"), "source": lead.get("source"),
                "url": lead.get("url"), "status": "NEEDS_HUMAN",
                "reason": "salary requires manual review",
            })
            stats["needs_human"] += 1
            continue
        # QA applications are opt-in: prioritize the candidate's primary
        # Frontend / HTML-CSS roles instead of silently submitting QA.
        # QA vacancies remain visible in reports for later review.
        if not freelance and _role_category(lead) == "qa" and os.getenv("AUTO_APPLY_QA", "0").strip().lower() not in ("1", "true", "yes"):
            results.append({
                "title": lead.get("title"),
                "source": lead.get("source"),
                "url": lead.get("url"),
                "status": "SKIPPED",
                "reason": "qa_auto_apply_disabled",
            })
            stats["skipped"] += 1
            continue
        # Discovery-only freelance boards have no supported direct submission.
        # Keep them in the separate Telegram shortlist, not in application
        # attempts or NEEDS_CONFIRMATION counts.
        if freelance and _application_priority(lead) != 0:
            stats["discovery_only_skipped"] = stats.get("discovery_only_skipped", 0) + 1
            continue
        bucket = "freelance_submitted" if freelance else "jobs_submitted"
        bucket_limit = freelance_limit if freelance else job_limit

        # Do not stop the whole run when one category is full:
        # jobs and freelance have independent hourly limits.
        if bucket_limit is not None and stats[bucket] >= bucket_limit:
            stats["hourly_limit_skipped"] += 1
            continue

        lid = enqueue(lead)

        if was_submitted(lid):
            stats["duplicate_skipped"] += 1
            results.append({
                "id": lid,
                "title": lead.get("title"),
                "status": "SKIPPED",
                "reason": "already_submitted",
            })
            continue

        if weekly_total_limit is not None and weekly_submitted_count >= weekly_total_limit:
            stats["weekly_limit_skipped"] = stats.get("weekly_limit_skipped", 0) + 1
            results.append({"id": lid, "title": lead.get("title"), "source": lead.get("source"),
                            "url": lead.get("url"), "status": "SKIPPED", "reason": "weekly_total_limit"})
            continue

        if total_daily_limit is not None and submitted_count >= total_daily_limit:
            stats["daily_limit_skipped"] += 1
            results.append({"id": lid, "title": lead.get("title"), "source": lead.get("source"),
                            "url": lead.get("url"), "status": "SKIPPED", "reason": "daily_total_limit"})
            continue
        if total_hourly_limit is not None and stats["submitted"] >= total_hourly_limit:
            stats["hourly_limit_skipped"] += 1
            results.append({"id": lid, "title": lead.get("title"), "source": lead.get("source"),
                            "url": lead.get("url"), "status": "SKIPPED", "reason": "hourly_total_limit"})
            continue
        if daily_limits[bucket] is not None and daily_counts[bucket] >= daily_limits[bucket]:
            stats["daily_limit_skipped"] += 1
            results.append({
                "id": lid,
                "title": lead.get("title"),
                "status": "SKIPPED",
                "reason": "daily_application_limit",
            })
            continue

        browser_scope = _browser_scope(lead)
        if browser_scope and browser_challenge_streak.get(browser_scope, 0) >= 2:
            stats["browser_challenge_paused"] += 1
            stats["skipped"] += 1
            results.append({
                "id": lid, "title": lead.get("title"),
                "source": lead.get("source"), "url": lead.get("url"),
                "status": "SKIPPED", "reason": "browser_challenge_pause",
            })
            continue

        # Alerts describe matched vacancies, regardless of whether this run
        # merely prepares a draft or sends an application.
        if should_notify(lead):
            notifications.append({
                "title": lead.get("title"),
                "source": lead.get("source"),
                "url": lead.get("url"),
                "match_score": lead.get("match_score"),
                "message": format_notification(lead),
            })

        # Never generate an application from an invented or missing candidate profile.
        if not load_resume_text():
            set_state(lid, "NEEDS_HUMAN")
            stats["needs_human"] += 1
            results.append({
                "id": lid,
                "title": lead.get("title"),
                "source": lead.get("source"),
                "url": lead.get("url"),
                "status": "NEEDS_HUMAN",
                "reason": "verified_resume_missing",
            })
            continue

        if dry_run:
            proposal = make_proposal(lead)
            stats["drafted"] += 1
            results.append({"id": lid, "title": lead.get("title"), "source": lead.get("source"),
                            "url": lead.get("url"), "status": "DRAFT", "reason": "dry_run",
                            "proposal": proposal})
            continue

        try:
            set_state(lid, "SHORTLISTED")
            proposal = make_proposal(lead)
            result = dispatch(lead, proposal)
            state = result["status"]
            if browser_scope:
                streak = (browser_challenge_streak.get(browser_scope, 0) + 1
                          if result.get("reason") in challenge_reasons else 0)
                browser_challenge_streak[browser_scope] = streak
                if streak >= 2:
                    browser_pause_active = True
                    if browser_scope not in stats["paused_browser_hosts"]:
                        stats["paused_browser_hosts"].append(browser_scope)
            set_state(lid, state)

            if state == "SUBMITTED":
                submitted_count += 1
                weekly_submitted_count += 1
                daily_counts[bucket] += 1
                stats["submitted"] += 1
                stats[bucket] += 1
                role = "freelance" if freelance else _role_category(lead)
                if role in stats["submitted_by_role"]:
                    stats["submitted_by_role"][role] += 1
                if browser_pause_active and (lead.get("apply_email") or str(lead.get("apply_url") or "").startswith("mailto:")):
                    stats["email_submitted_after_browser_pause"] += 1
            else:
                key = state.lower()
                if key in stats:
                    stats[key] += 1
                elif state == "NEEDS_HUMAN":
                    stats["needs_human"] += 1
                else:
                    stats["skipped"] += 1

            results.append({
                "id": lid,
                "title": lead.get("title"),
                "source": lead.get("source"),
                "url": lead.get("url"),
                "score": lead.get("profit_score"),
                "match_score": lead.get("match_score"),
                "match_reason": lead.get("match_reason"),
                "resume_skills_match": lead.get("resume_skills_match", []),
                "matched_skills": lead.get("matched_skills", []),
                **result,
            })
        except Exception as exc:
            print(f"[dispatch-error] {lead.get('source')} {lead.get('url')}: {exc!r}", flush=True)
            traceback.print_exc()
            set_state(lid, "FAILED")
            stats["failed"] += 1
            results.append({
                "id": lid,
                "title": lead.get("title"),
                "status": "FAILED",
                "source": lead.get("source"),
                "url": lead.get("url"),
                "reason": f"{type(exc).__name__}: {str(exc)[:120]}",
            })

    # Report actual submission capability separately from discovered listings.
    freelance_actionable = [
        lead for lead in ranked_freelance
        if _application_priority(lead) == 0
    ]
    stats["freelance_actionable"] = len(freelance_actionable)
    stats["freelance_discovery_only"] = stats["freelance_ranked"] - len(freelance_actionable)
    stats["freelancehunt_token_configured"] = bool(os.getenv("FREELANCEHUNT_TOKEN"))
    stats["smtp_configured"] = all(os.getenv(key) for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))
    stats["remote_job_identity_configured"] = (
        bool(os.getenv("REMOTE_JOB_NAME")) and bool(os.getenv("REMOTE_JOB_PHONE"))
        and bool(os.getenv("REMOTE_JOB_EMAIL") or os.getenv("SMTP_USER"))
    )

    # Show matching employment vacancies independently of freelance projects.
    job_review = sorted(
        (lead for lead in ranked_jobs if lead.get('url')),
        key=lambda lead: (
            0 if lead.get("opportunity_type") == "paid_placement" else 1,
            ROLE_PRIORITY.get(_role_category(lead), 99),
            _application_priority(lead),
            -lead.get("profit_score", 0),
        ),
    )[:10]
    stats['job_ranked'] = len(ranked_jobs)
    stats['job_actionable'] = sum(_application_priority(lead) == 0 for lead in ranked_jobs)
    outreach_drafts = build_outreach_drafts(job_review, limit=10)
    outreach_ids = save_outreach_drafts(outreach_drafts)
    stats["outreach_drafts_prepared"] = len(outreach_drafts)
    stats["outreach_drafts_saved"] = len(outreach_ids)
    stats["outreach_sent"] = sum(bool(item.get("contacted_at")) for item in list_outreach(limit=500))
    stats["outreach_replied"] = sum(item["status"] in ("REPLIED", "INTERVIEW", "REJECTED", "OFFER") for item in list_outreach(limit=500))
    if job_review:
        lines = ['Вакансии Junior Frontend / вёрстка / QA — Россия и мир:',
                 'Ссылки на вакансии; отправка откликов здесь не подтверждается.']
        for lead in job_review:
            lines.append(f"- {str(lead.get('title') or 'Вакансия')[:85]} [{lead.get('source') or '?'}]\n{lead['url']}")
        try:
            _suppress_telegram_message('\n'.join(lines))
        except Exception as exc:
            print(f'[telegram] job shortlist: {type(exc).__name__}', flush=True)

    # Report promising freelance projects even when bidding is not supported.
    # Prefer marketplaces where a direct application path may exist, rather
    # than filling the whole shortlist with ProLinker discovery-only cards.
    freelance_review = []
    if not ranked_jobs:
        freelance_review = sorted(
            (lead for lead in ranked_freelance if lead.get("url")),
            key=lambda lead: (
                0 if lead.get("apply_email") else
                1 if lead.get("source") == "freelancehunt" and lead.get("can_api_bid") else
                2 if lead.get("source") in ("fl_ru", "habr_freelance") else
                3 if lead.get("source") == "peopleperhour" else 4,
                -lead.get("profit_score", 0),
            ),
        )[:5]
    freelance_review_delivery = None
    if freelance_review:
        lines = ["Фриланс: подходящие заказы (ссылки; отклики НЕ отправлены):"]
        for lead in freelance_review:
            lines.append(f"- {str(lead.get('title') or 'Заказ')[:100]}\n{lead['url']}")
        try:
            freelance_review_delivery = _suppress_telegram_message("\n".join(lines))
        except Exception as exc:
            freelance_review_delivery = {"status": "FAILED", "reason": type(exc).__name__}

    # Alert about blocked applications with the direct destination URL.
    budget_review = [item for item in results if item.get("reason") == "bid_price_missing_or_invalid"]
    if budget_review:
        lines = ["Уточнить бюджет: ставки НЕ отправлены:"]
        for item in budget_review:
            lines.append(f"- {str(item.get('title') or 'Проект')[:90]}\n{item.get('url') or ''}")
        try:
            _suppress_telegram_message("\n".join(lines))
        except Exception as exc:
            print(f"[telegram] budget review notification: {type(exc).__name__}", flush=True)

    blocked = [item for item in results if item.get("status") in ("NEEDS_HUMAN", "NEEDS_CONFIRMATION")
               and item.get("reason") != "bid_price_missing_or_invalid"]
    if blocked:
        lines = ["Требуется действие: отклики НЕ отправлены:", "При Turnstile открой ссылку, пройди проверку и отправь отклик на сайте. При HTTP 429 не обновляй страницу многократно: сайт ограничивает запросы."]
        for item in blocked[:10]:
            lines.append(
                f"- {str(item.get('title') or 'Вакансия')[:90]} "
                f"({item.get('reason') or 'требуется проверка'})\n"
                f"{item.get('apply_url') or item.get('url') or ''}"
            )
        try:
            _suppress_telegram_message("\n".join(lines))
        except Exception as exc:
            print(f"[telegram] blocked notification: {type(exc).__name__}", flush=True)

    deliveries = deliver_notifications(notifications)
    stats["origin_diagnostics"] = origin_diagnostics()
    stats["captcha_count"] = sum(item.get("reason") in challenge_reasons for item in results)
    stats["rate_limited_count"] = sum(item.get("reason") == "aggregator_rate_limited" for item in results)
    stats["missing_bid_price_count"] = len(budget_review)
    stats["duplicates_skipped"] = stats["duplicate_skipped"] + sum(
        item.get("reason") == "already_applied_on_hh" for item in results
    )
    stats["notifications"] = len(notifications)
    stats["notifications_sent"] = sum(
        1 for item in deliveries if item.get("status") == "SENT"
    )
    stats["dry_run"] = dry_run
    stats["daily_total_limit"] = total_daily_limit
    stats["hourly_total_limit"] = total_hourly_limit
    stats["daily_application_limit"] = daily_limit
    stats["hourly_job_limit"] = job_limit
    stats["hourly_freelance_limit"] = freelance_limit
    stats["submitted_today_total"] = submitted_count
    stats["jobs_submitted_today"] = daily_counts["jobs_submitted"]
    stats["freelance_submitted_today"] = daily_counts["freelance_submitted"]
    stats["daily_job_limit"] = daily_limits["jobs_submitted"]
    stats["daily_freelance_limit"] = daily_limits["freelance_submitted"]

    detail_lines = []
    # Lead with Frontend/layout and freelance blockers, not disabled QA.
    display_results = sorted(
        results,
        key=lambda item: (
            1 if item.get("reason") == "qa_auto_apply_disabled" else 0,
            0 if item.get("status") in ("SUBMITTED", "NEEDS_HUMAN", "NEEDS_CONFIRMATION") else 1,
        ),
    )
    for item in display_results[:8]:
        title = str(item.get("title") or "Untitled")[:80]
        source = str(item.get("source") or "?")
        status = str(item.get("status") or "?")
        reason = str(item.get("reason") or "")
        url = str(item.get("url") or "")
        detail_lines.append(f"- {title} [{source}] — {status}" + (f" ({reason})" if reason else ""))
        # Include sanitized form errors; never expose candidate identity or credentials.
        detail = str(item.get("detail") or "")
        if detail and reason == "remote_job_form_validation_error":
            detail_lines.append("  Form error: " + detail[:240])
        if reason == "unknown_employer_question":
            questions = item.get("unanswered_questions") or ([detail] if detail else [])
            for question in questions[:10]:
                detail_lines.append("  HH employer question (answer required): " + str(question).replace("\n", " ")[:300])
        if url:
            detail_lines.append(url)

    summary_message = (
        "Job Auto Apply — all sources report\n" +
        f"Run: {os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/{os.getenv('GITHUB_REPOSITORY', 'unknown')}/actions/runs/{os.getenv('GITHUB_RUN_ID', 'unknown')}\n"
        f"Workflow: {os.getenv('GITHUB_WORKFLOW', 'unknown')} | Ref: {os.getenv('GITHUB_REF_NAME', 'unknown')} | SHA: {os.getenv('GITHUB_SHA', 'unknown')[:12]}\n"
        f"Found: {stats['found']}\n"
        f"Raw discovered: {stats['raw_found']}\n"
        f"Fresh unique: {stats['fresh_unique']}\n"
        f"Unique checked: {stats['unique_checked']}\n"
        f"After filters: {stats['ranked']}\n"
        f"Fresh found: {stats['fresh_found']}\n"
        f"Fresh + saved leads checked: {stats['backlog_rechecked']}\n"
        f"Full descriptions read: {stats['descriptions_enriched']}\n"
        f"Frontend found: {stats['frontend_found']}\n"
        f"Layout found: {stats['layout_found']}\n"
        f"QA found: {stats['qa_found']}\n"
        f"Job vacancies ranked: {stats['job_ranked']}\n"
        f"Job actionable channels: {stats['job_actionable']}\n"
        f"Freelance found: {stats['freelance_found']}\n"
        f"Freelance ranked: {stats['freelance_ranked']}\n"
        f"Freelance actionable channels: {stats['freelance_actionable']}\n"
        f"Freelance discovery-only: {stats['freelance_discovery_only']}\n"
        f"Freelancehunt API configured: {stats['freelancehunt_token_configured']}\n"
        f"SMTP configured: {stats['smtp_configured']}\n"
        f"Remote-job identity configured: {stats['remote_job_identity_configured']}\n"
        f"Freelance configured limit: {_limit_label(freelance_limit)} (HOURLY_FREELANCE_LIMIT)\n"
        f"QA auto-apply: {os.getenv('AUTO_APPLY_QA', '0')}\n"
        f"Ranked: {stats['ranked']}\n"
        f"Mode: {'DRAFT — no applications sent' if dry_run else 'LIVE'}\n"
        f"Drafts prepared: {stats['drafted']}\n"
        f"Daily total cap: {_limit_label(total_daily_limit)} | Hourly total cap: {_limit_label(total_hourly_limit)}\n"
        f"Submitted by role (React/frontend, layout, QA): {stats['submitted_by_role']['frontend']}, {stats['submitted_by_role']['layout']}, {stats['submitted_by_role']['qa']}\n"        "Refusals/invitations by role: not synchronized with HH or email (unknown)\n"
        f"Jobs submitted this run: {stats['jobs_submitted']}/{_limit_label(stats['hourly_job_limit'])}\n"
        f"Freelance submitted this run: {stats['freelance_submitted']}/{_limit_label(stats['hourly_freelance_limit'])}\n"
        f"Submitted this run total: {stats['submitted']}\n"
        f"Skipped: {stats['skipped'] + stats['duplicate_skipped'] + stats['daily_limit_skipped'] + stats['hourly_limit_skipped']}\n"
        f"Failed: {stats['failed']}\n"
        f"Needs human: {stats['needs_human']}\n"
        f"Shortlisted (not sent): {stats['shortlisted']}\n"
        f"Needs confirmation: {stats['needs_confirmation']}\n"
        f"Captcha blockers: {stats['captcha_count']}\n"
        f"Rate-limited leads (429): {stats['rate_limited_count']}\n"
        f"Duplicates skipped: {stats['duplicates_skipped']}\n"
        f"No bid price: {stats['missing_bid_price_count']}\n"
        f"Browser paused after two challenges: {stats['browser_challenge_paused']}\n"
        f"Paused browser hosts: {', '.join(stats['paused_browser_hosts']) or 'none'}\n"
        f"Email submitted after browser pause: {stats['email_submitted_after_browser_pause']}\n"
        f"Paid placements ranked: {stats['paid_placements_ranked']}\n"
        f"Aggregator origin requests: {stats['origin_diagnostics']['origin_requests']}\n"
        f"Aggregator adverts deferred after 429: {stats['origin_diagnostics']['deferred_adverts']}\n"
        f"First aggregator 429: {stats['origin_diagnostics']['first_429'] or 'none'}\n"
        f"Telegram vacancy alerts sent: {stats['notifications_sent']}\n"
        f"Jobs submitted today: {stats['jobs_submitted_today']}/{_limit_label(stats['daily_job_limit'])}\n"
        f"Freelance submitted today: {stats['freelance_submitted_today']}/{_limit_label(stats['daily_freelance_limit'])}\n\n"
        "Results:\n" + ("\n".join(detail_lines) if detail_lines else "No ranked results")
    )
    # Funnel conversion uses confirmed submissions, never discovered links.
    eligible_jobs = stats['job_ranked']
    submitted_jobs = stats['jobs_submitted']
    job_conversion = 100.0 * submitted_jobs / eligible_jobs if eligible_jobs else 0.0
    summary_message += (
        '\n\nEmployment funnel (this run):'
        f"\nDiscovered non-freelance: {sum(not is_freelance(lead) for lead in leads)}"
        f"\nEligible non-freelance: {eligible_jobs}"
        f"\nConfirmed applications: {submitted_jobs}"
        f"\nEligible-to-submitted conversion: {job_conversion:.1f}%"
        '\nEmployer replies / interviews / offers: not synchronized (unknown)'
    )
    if eligible_jobs and not submitted_jobs:
        summary_message += '\nPriority: fix application channels before expanding discovery.'

    summary_message += "\n\nFilters by role:" + "".join(
        f"\n- {role}: found {data['found']}, eligible {data['eligible']}; rejected: " +
        (", ".join(f"{reason}={count}" for reason, count in data["rejected_reasons"].items()) or "none")
        for role, data in eligibility.items()
    )
    summary_message += "\n\nSources: " + ", ".join(f"{name}: {count}" for name, count in source_counts.items())
    from collections import Counter
    reasons = Counter(str(item.get("reason") or item.get("status") or "unknown") for item in results if item.get("status") != "SUBMITTED")
    if reasons:
        summary_message += "\nReasons: " + "; ".join(f"{reason}: {count}" for reason, count in reasons.most_common(8))
    if dry_run:
        drafts = [item for item in results if item.get("status") == "DRAFT"]
        summary_message += "\n\nDraft examples (NOT sent):" + ("".join(
            f"\n- {item.get('title')} [{item.get('source')}]\n{item.get('url')}\n{item.get('proposal')}"
            for item in drafts[:5]) if drafts else "\nNone")
    if budget_review:
        summary_message += "\nУточнить бюджет (ставки не отправлены):" + "".join(
            f"\n- {str(item.get('title') or 'Проект')[:80]}\n{item.get('url') or ''}" for item in budget_review[:5]
        )
    if freelance_review:
        summary_message += "\nFreelance shortlist: five links sent separately (not applications)."
    if COLLECTION_ERRORS:
        summary_message += "\nSource errors: " + "; ".join(f"{item['source']}: {item['reason']}" for item in COLLECTION_ERRORS)
    if not stats["resume_configured"]:
        summary_message += "\nResume matching: not configured"
    summary_message = (
        "Job Auto Apply — сводка\n"
        f"Найдено объявлений: {stats['found']}\n"
        f"Подходящих после фильтров: {stats['ranked']}\n"
        f"Отправлено откликов: {stats['submitted']}\n"
        f"Подготовлено черновиков: {stats['drafted']}\n"
        f"Требуется ваше участие: {stats['needs_human'] + stats['needs_confirmation']}\n"
        f"Пропущено: {stats['skipped'] + stats['duplicate_skipped'] + stats['daily_limit_skipped'] + stats['hourly_limit_skipped']}\n"
        f"Ошибок: {stats['failed']}\n"
        "Вакансии — приоритет. Фриланс используется только если подходящих вакансий нет."
    )
    # Work-format visibility: compare all checked employment leads with those
    # surviving the ranker, and count drafts separately when DRY_RUN is active.
    from collections import Counter
    format_labels = {
        "remote": "удалёнка",
        "hybrid": "гибрид",
        "office": "офис",
        "unknown": "формат не указан",
    }
    checked_formats = Counter(_work_mode(lead) for lead in job_leads)
    eligible_formats = Counter(_work_mode(lead) for lead in ranked_jobs)
    drafted_urls = {
        str(item.get("url") or "")
        for item in results
        if item.get("status") == "DRAFT" and item.get("url")
    }
    drafted_formats = Counter(
        _work_mode(lead) for lead in ranked_jobs
        if str(lead.get("url") or "") in drafted_urls
    )
    summary_message += "\n\\nФОРМАТ РАБОТЫ (вакансии):"
    for mode in ("remote", "hybrid", "office", "unknown"):
        label = format_labels[mode]
        summary_message += (
            f"\n- {label}: проверено {checked_formats[mode]}, "
            f"прошло фильтры {eligible_formats[mode]}, "
            f"черновиков {drafted_formats[mode]}"
        )
    summary_message += "\nУдалёнка, гибрид и офис учитываются по всей России; "
    summary_message += "формат не указан — отдельно, без автоматического приравнивания к удалёнке. "
    summary_message += "Черновики не отправлены."
    summary_message += "\n\n" + build_market_report(job_leads)
    summary_message += "\n\n" + build_filter_report(job_leads)
    manual_review_items = build_manual_review_list(job_leads, limit=10)
    if manual_review_items:
        summary_message += "\n\nПОГРАНИЧНЫЕ ВАКАНСИИ — РУЧНАЯ ПРОВЕРКА (НЕ ОТКЛИКАТЬСЯ АВТОМАТИЧЕСКИ):"
        for item in manual_review_items:
            ats = f" — ATS {item['ats_score']}/100" if isinstance(item.get("ats_score"), (int, float)) else ""
            summary_message += (
                f"\n- {item['title']} [{item['source']}]{ats}"
                f"\nПричина: {item['reason']}"
                f"\n{item['url']}"
            )
    summary_message += "\n\n" + build_outcome_feedback_report()
    if salary_review_jobs:
        summary_message += "\n\nРучная проверка зарплаты — отклики НЕ отправляются:"
        for lead in salary_review_jobs[:10]:
            summary_message += (
                f"\n- {str(lead.get('title') or 'Вакансия')[:90]} "
                f"[{lead.get('source') or '?'}] — зарплата не указана или требует уточнения"
                f"\n{lead.get('url')}"
            )
    if ranked_jobs:
        summary_message += "\n\nПодходящие вакансии:"
        for lead in ranked_jobs[:5]:
            summary_message += f"\n- {str(lead.get('title') or 'Вакансия')[:90]} [{lead.get('source') or '?'}] — ATS {lead.get('ats_score', 'н/д')}/100 ({lead.get('ats_verdict', 'н/д')})\n{lead.get('url') or ''}"
        if outreach_drafts:
            summary_message += "\n\nПрямой контакт с компаниями — ЧЕРНОВИКИ, НЕ ОТПРАВЛЕНЫ:"
            for draft in outreach_drafts:
                summary_message += (
                    f"\n\n{draft['company']} — {draft['title']}"
                    f"\nКонтакт руководителя: {draft['people_search_url']}"
                    f"\nСайт/контакты компании: {draft['company_search_url']}"
                    f"\nВакансия: {draft['vacancy_url']}"
                    f"\nТекст сообщения: {draft['message_draft']}"
                )
    elif freelance_review:
        summary_message += "\n\nФриланс — резервный вариант:"
        for lead in freelance_review[:5]:
            summary_message += f"\n- {str(lead.get('title') or 'Заказ')[:90]} [{lead.get('source') or '?'}]\n{lead.get('url') or ''}"
    try:
        summary_delivery = send_message(summary_message)
    except Exception as exc:
        summary_delivery = {
            "status": "FAILED",
            "reason": type(exc).__name__,
        }

    print(f"[telegram] summary delivery: {summary_delivery}", flush=True)
    return {
        "stats": stats,
        "results": results,
        "notifications": notifications,
        "notification_deliveries": deliveries,
        "freelance_review_delivery": freelance_review_delivery,
        "summary_delivery": summary_delivery,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))

