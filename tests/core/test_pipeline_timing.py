"""Integration test: timing layer instruments pipeline-like flows (M3 PR2).

Proves that the PhaseTimer/TimingCollector produces a complete JobTimingReport
with mandatory/optional separation and degradation flagging — the prerequisite
for any honest "five-minute SLO" claim (U3-LATENCY-PROFILE).
"""

from __future__ import annotations

import pytest

from udify.core.infrastructure.timer import TimingCollector
from udify.core.infrastructure.timing import PhaseCategory


def test_pipeline_phases_produce_complete_report():
    """Simulate the real pipeline phases and verify the report decomposes them."""
    collector = TimingCollector()
    # Simulate mandatory phases (perception, validation, apply).
    with collector.phase("perception", PhaseCategory.MANDATORY, {"files": 42}):
        pass
    with collector.phase("validation", PhaseCategory.MANDATORY, {"assertions": 5}):
        pass
    with collector.phase("apply", PhaseCategory.MANDATORY, {"operations": 12}):
        pass
    # Simulate optional phases (llm, extra mcts rollout).
    with collector.phase("llm_intent", PhaseCategory.OPTIONAL, {"tokens": 1500}):
        pass
    with collector.phase("mcts_extra", PhaseCategory.OPTIONAL, {"rollouts": 200}):
        pass

    report = collector.build_report("job-123")
    assert report.job_id == "job-123"
    assert report.total_ms >= 0
    # mandatory + optional must sum to total
    assert report.mandatory_ms + report.optional_ms == pytest.approx(report.total_ms, abs=1)
    assert len(report.phases) == 5
    mandatory_names = {p.phase for p in report.phases if p.category is PhaseCategory.MANDATORY}
    assert mandatory_names == {"perception", "validation", "apply"}
    assert report.degraded is False


def test_optional_budget_overflow_marks_degraded():
    collector = TimingCollector()
    # Spend optional time exceeding budget.
    with collector.phase("llm", PhaseCategory.OPTIONAL, {}):
        pass
    # A zero/near-zero budget should flag overflow.
    assert collector.check_optional_budget(0.0) is False


def test_optional_budget_within_limit_ok():
    collector = TimingCollector()
    with collector.phase("llm", PhaseCategory.OPTIONAL, {}):
        pass
    # Generous budget should be OK.
    assert collector.check_optional_budget(999999.0) is True


def test_report_detail_preserves_phase_metadata():
    collector = TimingCollector()
    with collector.phase("perception", PhaseCategory.MANDATORY, {"files": 99, "bytes": 4096}):
        pass
    report = collector.build_report("j1")
    perception = report.phases[0]
    assert perception.detail["files"] == 99
    assert perception.detail["bytes"] == 4096


def test_report_frozen():
    collector = TimingCollector()
    with collector.phase("p", PhaseCategory.MANDATORY, {}):
        pass
    report = collector.build_report("j1")
    with pytest.raises(AttributeError):
        report.total_ms = 999  # type: ignore[misc]
