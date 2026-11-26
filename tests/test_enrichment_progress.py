from unittest.mock import patch

import worker


def test_enrichment_progress_preserves_input_order_and_logs_batches():
    leads = [{"id": index} for index in range(23)]
    def enrich(lead):
        return {**lead, "enriched": True}

    with patch("builtins.print") as output:
        result = worker._enrich_with_progress(leads, enrich, stage="test", max_workers=3)

    assert [lead["id"] for lead in result] == list(range(23))
    assert all(lead["enriched"] for lead in result)
    messages = [call.args[0] for call in output.call_args_list]
    assert messages[0] == "[enrichment] test: starting candidates=23 workers=3"
    assert "[enrichment] test: progress=10/23" in messages
    assert "[enrichment] test: progress=20/23" in messages
    assert "[enrichment] test: progress=23/23" in messages
    assert messages[-1] == "[enrichment] test: complete=23"


def test_empty_enrichment_batch_is_reported_without_starting_workers():
    with patch("builtins.print") as output:
        assert worker._enrich_with_progress([], lambda lead: lead) == []
    output.assert_called_once_with("[enrichment] jobs: no candidates", flush=True)

