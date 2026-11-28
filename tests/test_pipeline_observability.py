from pipeline_observability import build_pipeline_stage_results


def test_pipeline_stage_results_report_funnel_and_partial_source_failures():
    candidates = [{"source": "hh"}, {"source": "jobicy"}]
    enriched = [
        {"source": "hh", "enriched": True},
        {"source": "jobicy", "enrichment_error": "HTTP 403", "unavailable": True},
    ]
    assessed = [{"source": "hh"}]
    ranked = []
    results = [{"status": "NEEDS_HUMAN", "reason": "verified_resume_missing"}]

    stages = build_pipeline_stage_results(
        candidates, enriched, assessed, ranked, results,
        collection_errors=[{"source": "hh", "reason": "HTTP 403"}],
    )

    assert [stage["stage"] for stage in stages] == [
        "collect", "enrich", "assess", "rank", "draft"
    ]
    assert stages[0]["status"] == "partial"
    assert stages[0]["reason_counts"] == {"source_error": 1}
    assert stages[1]["status"] == "partial"
    assert stages[1]["reason_counts"] == {
        "enrichment_error": 1, "vacancy_unavailable": 1
    }
    assert stages[2]["input_count"] == 2
    assert stages[2]["output_count"] == 1
    assert stages[3]["reason_counts"] == {"rank_rejected": 1}
    assert stages[4]["reason_counts"] == {"human_review_required": 1}


def test_pipeline_stage_results_do_not_leak_candidate_content():
    secret = "PRIVATE RESUME AND VACANCY TEXT"
    stages = build_pipeline_stage_results(
        [{"description": secret}], [{"description": secret}],
        [{"description": secret}], [], [{"status": "DRAFT", "proposal": secret}],
    )
    serialized = repr(stages)
    assert secret not in serialized
    assert "description" not in serialized
    assert "proposal" not in serialized


def test_empty_pipeline_is_valid_and_draft_count_is_explicit():
    stages = build_pipeline_stage_results([], [], [], [], [])
    assert all(stage["status"] == "ok" for stage in stages)
    assert [stage["output_count"] for stage in stages] == [0, 0, 0, 0, 0]


def test_successful_drafts_are_counted_without_exposing_text():
    stages = build_pipeline_stage_results(
        [{"source": "hh"}], [{"source": "hh"}], [{"source": "hh"}],
        [{"source": "hh"}],
        [{"status": "DRAFT", "proposal": "candidate-specific content"}],
    )
    assert stages[-1]["output_count"] == 1
    assert stages[-1]["status"] == "ok"
