"""Shared, privacy-safe contract for observable pipeline stages.

Stage results describe execution metadata only. Item payloads are deliberately
excluded so callers cannot accidentally serialize resumes, vacancy text, or
cover-letter drafts into logs and notifications.
"""

from dataclasses import asdict, dataclass, field
import re
from typing import Mapping, Optional

STAGE_STATUSES = frozenset({"ok", "partial", "blocked", "error"})
_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,79}$")


def _count(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _reason_counts(values):
    result = {}
    for code, count in (values or {}).items():
        if not isinstance(code, str) or not _CODE_PATTERN.fullmatch(code):
            raise ValueError(f"invalid reason code: {code!r}")
        result[code] = _count(count, f"reason_counts[{code!r}]")
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class StageResult:
    """Immutable summary for one pipeline stage; never contains lead payloads."""

    stage: str
    status: str
    input_count: int
    output_count: int
    reason_counts: Mapping[str, int] = field(default_factory=dict)
    duration_ms: Optional[int] = None
    warnings: tuple = ()

    def __post_init__(self):
        if not isinstance(self.stage, str) or not _CODE_PATTERN.fullmatch(self.stage):
            raise ValueError("stage must be a stable lowercase identifier")
        if self.status not in STAGE_STATUSES:
            raise ValueError(f"unsupported stage status: {self.status!r}")
        _count(self.input_count, "input_count")
        _count(self.output_count, "output_count")
        if self.duration_ms is not None:
            _count(self.duration_ms, "duration_ms")
        object.__setattr__(self, "reason_counts", _reason_counts(self.reason_counts))
        normalized_warnings = tuple(self.warnings or ())
        for warning in normalized_warnings:
            if not isinstance(warning, str) or not _CODE_PATTERN.fullmatch(warning):
                raise ValueError(f"invalid warning code: {warning!r}")
        object.__setattr__(self, "warnings", normalized_warnings)

    def to_dict(self):
        """Return JSON-friendly metadata without any source or candidate text."""
        data = asdict(self)
        data["warnings"] = list(self.warnings)
        return data


def make_stage_result(
    stage,
    input_count,
    output_count,
    *,
    reason_counts=None,
    duration_ms=None,
    warnings=(),
    blocked=False,
    error_count=0,
):
    """Build a stage result with consistent partial/error classification."""
    _count(input_count, "input_count")
    _count(output_count, "output_count")
    _count(error_count, "error_count")
    if blocked:
        status = "blocked"
    elif error_count and output_count:
        status = "partial"
    elif error_count:
        status = "error"
    else:
        status = "ok"
    return StageResult(
        stage=stage,
        status=status,
        input_count=input_count,
        output_count=output_count,
        reason_counts=reason_counts or {},
        duration_ms=duration_ms,
        warnings=tuple(warnings or ()),
    )
