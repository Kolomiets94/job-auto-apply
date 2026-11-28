"""Build safe, stable stage diagnostics for one worker run."""

from collections import Counter

from stage_result import make_stage_result


def _error_count(items):
    return sum(bool(item.get("enrichment_error")) for item in items)


def build_pipeline_stage_results(
    candidates, enriched, assessed, ranked, results, collection_errors=None
):
    """Return ordered stage summaries; never serialize lead or candidate text."""
    candidates = list(candidates or [])
    enriched = list(enriched or [])
    assessed = list(assessed or [])
    ranked = list(ranked or [])
    results = list(results or [])
    collection_errors = list(collection_errors or [])

    collection_reasons = Counter()
    if collection_errors:
        collection_reasons["source_error"] = len(collection_errors)

    enrichment_reasons = Counter()
    for item in enriched:
        if item.get("unavailable"):
            enrichment_reasons["vacancy_unavailable"] += 1
        if item.get("enrichment_error"):
            enrichment_reasons["enrichment_error"] += 1

    assessed_reasons = Counter()
    for item in assessed:
        if item.get("unavailable"):
            assessed_reasons["vacancy_unavailable"] += 1

    ranked_reasons = Counter()
    rejected_count = max(0, len(assessed) - len(ranked))
    if rejected_count:
        ranked_reasons["rank_rejected"] = rejected_count

    draft_reasons = Counter()
    draft_count = 0
    for item in results:
        status = str(item.get("status") or "").upper()
        reason = str(item.get("reason") or "")
        if status == "DRAFT":
            draft_count += 1
        elif status in {"FAILED", "ERROR"}:
            draft_reasons["draft_error"] += 1
        elif status in {"NEEDS_HUMAN", "NEEDS_CONFIRMATION"}:
            draft_reasons["human_review_required"] += 1
        elif status == "SKIPPED":
            draft_reasons["draft_skipped"] += 1

    collection_error_count = len(collection_errors)
    enrichment_error_count = _error_count(enriched)
    return [
        make_stage_result(
            "collect", len(candidates), len(candidates),
            reason_counts=collection_reasons,
            error_count=collection_error_count,
        ).to_dict(),
        make_stage_result(
            "enrich", len(candidates),
            sum(not item.get("unavailable") for item in enriched),
            reason_counts=enrichment_reasons,
            error_count=enrichment_error_count,
        ).to_dict(),
        make_stage_result(
            "assess", len(enriched), len(assessed),
            reason_counts=assessed_reasons,
        ).to_dict(),
        make_stage_result(
            "rank", len(assessed), len(ranked),
            reason_counts=ranked_reasons,
        ).to_dict(),
        make_stage_result(
            "draft", len(ranked), draft_count,
            reason_counts=draft_reasons,
            error_count=draft_reasons.get("draft_error", 0),
        ).to_dict(),
    ]
