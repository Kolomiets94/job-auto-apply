import pytest

from stage_result import StageResult, make_stage_result


def test_stage_result_serializes_only_safe_execution_metadata():
    result = make_stage_result(
        "collect",
        12,
        9,
        reason_counts={"source_timeout": 2, "source_forbidden": 1},
        duration_ms=125,
        warnings=("source_partial",),
        error_count=3,
    )

    assert result.status == "partial"
    assert result.to_dict() == {
        "stage": "collect",
        "status": "partial",
        "input_count": 12,
        "output_count": 9,
        "reason_counts": {"source_forbidden": 1, "source_timeout": 2},
        "duration_ms": 125,
        "warnings": ["source_partial"],
    }
    assert "resume" not in str(result.to_dict())
    assert "description" not in str(result.to_dict())


def test_empty_success_is_ok():
    result = make_stage_result("rank", 0, 0)
    assert result.status == "ok"
    assert result.output_count == 0


def test_all_failed_stage_is_error():
    result = make_stage_result("enrich", 8, 0, error_count=8)
    assert result.status == "error"


def test_explicit_blocked_stage_is_blocked():
    result = make_stage_result("draft", 4, 0, blocked=True)
    assert result.status == "blocked"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"input_count": -1, "output_count": 0},
        {"input_count": 1, "output_count": -1},
        {"input_count": True, "output_count": 0},
        {"input_count": 1, "output_count": 0, "error_count": -1},
    ],
)
def test_invalid_counts_are_rejected(kwargs):
    with pytest.raises(ValueError):
        make_stage_result("collect", **kwargs)


def test_invalid_reason_code_is_rejected():
    with pytest.raises(ValueError, match="invalid reason code"):
        StageResult("rank", "ok", 1, 0, {"Not Stable Reason": 1})


def test_invalid_warning_code_is_rejected():
    with pytest.raises(ValueError, match="invalid warning code"):
        StageResult("rank", "ok", 1, 0, warnings=("contains private detail",))


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError, match="unsupported stage status"):
        StageResult("rank", "running", 1, 0)
