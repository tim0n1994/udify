"""Tests for the Udify phase timing and collection layer."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

import udify.core.infrastructure.timer as timer_module
from udify.core.infrastructure.timer import PhaseTimer, TimingCollector
from udify.core.infrastructure.timing import (
    JobTimingReport,
    PhaseCategory,
    PhaseTiming,
)


def _patch_clock(
    monkeypatch: pytest.MonkeyPatch,
    values: tuple[float, ...],
) -> None:
    """Replace perf_counter with a deterministic sequence."""
    sequence: Iterator[float] = iter(values)
    monkeypatch.setattr(
        timer_module.time,
        "perf_counter",
        lambda: next(sequence),
    )


def _phase_from_dict(payload: Mapping[str, object]) -> PhaseTiming:
    """Reconstruct a phase timing from its serialized representation."""
    return PhaseTiming(
        phase=cast(str, payload["phase"]),
        category=PhaseCategory(cast(str, payload["category"])),
        duration_ms=cast(float, payload["duration_ms"]),
        detail=cast(Mapping[str, object], payload["detail"]),
    )


def _report_from_dict(payload: Mapping[str, object]) -> JobTimingReport:
    """Reconstruct a job report from its serialized representation."""
    raw_phases = cast(list[Mapping[str, object]], payload["phases"])
    return JobTimingReport(
        job_id=cast(str, payload["job_id"]),
        total_ms=cast(float, payload["total_ms"]),
        mandatory_ms=cast(float, payload["mandatory_ms"]),
        optional_ms=cast(float, payload["optional_ms"]),
        phases=tuple(_phase_from_dict(item) for item in raw_phases),
        degraded=cast(bool, payload["degraded"]),
    )


def test_phase_category_values_are_stable() -> None:
    assert PhaseCategory.MANDATORY.value == "mandatory"
    assert PhaseCategory.OPTIONAL.value == "optional"


def test_phase_timing_rejects_empty_phase() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        PhaseTiming(
            phase=" ",
            category=PhaseCategory.MANDATORY,
            duration_ms=1.0,
        )


@pytest.mark.parametrize("duration_ms", [-1.0, float("inf"), float("nan")])
def test_phase_timing_rejects_invalid_duration(duration_ms: float) -> None:
    with pytest.raises(ValueError, match="finite, non-negative"):
        PhaseTiming(
            phase="perception",
            category=PhaseCategory.MANDATORY,
            duration_ms=duration_ms,
        )


def test_phase_timing_is_frozen() -> None:
    timing = PhaseTiming(
        phase="perception",
        category=PhaseCategory.MANDATORY,
        duration_ms=12.0,
    )

    with pytest.raises(FrozenInstanceError):
        timing.phase = "planner"


def test_phase_timing_detail_is_immutable() -> None:
    timing = PhaseTiming(
        phase="perception",
        category=PhaseCategory.MANDATORY,
        duration_ms=12.0,
        detail={"files": 10},
    )
    mutable_detail = cast(MutableMapping[str, object], timing.detail)

    with pytest.raises(TypeError):
        mutable_detail["files"] = 20


def test_phase_timing_to_dict_returns_independent_copy() -> None:
    timing = PhaseTiming(
        phase="perception",
        category=PhaseCategory.MANDATORY,
        duration_ms=12.5,
        detail={"files": 10},
    )

    payload = timing.to_dict()
    payload_detail = cast(dict[str, object], payload["detail"])
    payload_detail["files"] = 99

    assert timing.detail["files"] == 10
    assert payload == {
        "phase": "perception",
        "category": "mandatory",
        "duration_ms": 12.5,
        "detail": {"files": 99},
    }


def test_phase_timing_to_dict_round_trip() -> None:
    timing = PhaseTiming(
        phase="resolver",
        category=PhaseCategory.OPTIONAL,
        duration_ms=3.25,
        detail={"candidates": 4},
    )

    assert _phase_from_dict(timing.to_dict()) == timing


def test_phase_timer_records_deterministic_elapsed_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (10.0, 10.125))
    collector = TimingCollector()

    with collector.phase(
        "perception",
        PhaseCategory.MANDATORY,
        {"files": 10},
    ):
        pass

    report = collector.build_report("job-1")
    assert len(report.phases) == 1
    assert report.phases[0].duration_ms == 125.0
    assert report.phases[0].detail == {"files": 10}


def test_phase_timer_uses_empty_detail_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (1.0, 1.001))
    collector = TimingCollector()

    with collector.phase("sanitize", PhaseCategory.MANDATORY):
        pass

    assert collector.build_report("job-1").phases[0].detail == {}


def test_phase_timer_copies_input_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (2.0, 2.010))
    collector = TimingCollector()
    detail: dict[str, object] = {"files": 10}

    timer = collector.phase(
        "perception",
        PhaseCategory.MANDATORY,
        detail,
    )
    detail["files"] = 100

    with timer:
        pass

    assert collector.build_report("job-1").phases[0].detail["files"] == 10


def test_phase_timer_records_phase_when_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (5.0, 5.050))
    collector = TimingCollector()

    with (
        pytest.raises(ValueError, match="boom"),
        collector.phase("validator", PhaseCategory.MANDATORY),
    ):
        raise ValueError("boom")

    report = collector.build_report("job-1")
    assert len(report.phases) == 1
    assert report.phases[0].phase == "validator"
    assert report.phases[0].duration_ms == pytest.approx(50.0)


def test_phase_timer_does_not_suppress_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (3.0, 3.010))
    collector = TimingCollector()

    with (
        pytest.raises(RuntimeError, match="pipeline failure"),
        collector.phase("patch", PhaseCategory.MANDATORY),
    ):
        raise RuntimeError("pipeline failure")


def test_phase_timer_is_one_shot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (1.0, 1.010))
    collector = TimingCollector()
    timer = collector.phase("planner", PhaseCategory.OPTIONAL)

    with timer:
        pass

    with pytest.raises(RuntimeError, match="only be entered once"):
        timer.__enter__()


def test_phase_timer_rejects_exit_before_enter() -> None:
    collector = TimingCollector()
    timer = PhaseTimer(
        collector=collector,
        phase="planner",
        category=PhaseCategory.OPTIONAL,
    )

    with pytest.raises(RuntimeError, match="before it was entered"):
        timer.__exit__(None, None, None)


def test_phase_timer_rejects_backwards_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (10.0, 9.0))
    collector = TimingCollector()

    with (
        pytest.raises(RuntimeError, match="moved backwards"),
        collector.phase("planner", PhaseCategory.OPTIONAL),
    ):
        pass

    assert collector.build_report("job-1").phases == ()


def test_collector_classifies_mandatory_and_optional_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 0.100, 1.0, 1.025))
    collector = TimingCollector()

    with collector.phase("perception", PhaseCategory.MANDATORY):
        pass
    with collector.phase("llm_intent", PhaseCategory.OPTIONAL):
        pass

    report = collector.build_report("job-1")
    assert report.mandatory_ms == pytest.approx(100.0)
    assert report.optional_ms == pytest.approx(25.0)


def test_report_total_equals_sum_of_all_phases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(
        monkeypatch,
        (0.0, 0.010, 1.0, 1.020, 2.0, 2.030),
    )
    collector = TimingCollector()

    with collector.phase("sanitize", PhaseCategory.MANDATORY):
        pass
    with collector.phase("perception", PhaseCategory.MANDATORY):
        pass
    with collector.phase("planner", PhaseCategory.OPTIONAL):
        pass

    report = collector.build_report("job-1")
    phase_sum = sum(phase.duration_ms for phase in report.phases)

    assert report.total_ms == pytest.approx(phase_sum)
    assert report.total_ms == pytest.approx(60.0)


def test_build_report_contains_all_required_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (4.0, 4.015))
    collector = TimingCollector()

    with collector.phase(
        "resolver",
        PhaseCategory.MANDATORY,
        {"nodes": 80, "edges": 120},
    ):
        pass

    report = collector.build_report("job-complete")
    assert report.job_id == "job-complete"
    assert report.total_ms == pytest.approx(15.0)
    assert report.mandatory_ms == pytest.approx(15.0)
    assert report.optional_ms == 0.0
    assert report.degraded is False
    assert len(report.phases) == 1


def test_job_timing_report_is_frozen() -> None:
    report = JobTimingReport(
        job_id="job-1",
        total_ms=0.0,
        mandatory_ms=0.0,
        optional_ms=0.0,
        phases=(),
        degraded=False,
    )

    with pytest.raises(FrozenInstanceError):
        report.degraded = True


def test_job_timing_report_rejects_inconsistent_totals() -> None:
    phase = PhaseTiming(
        phase="perception",
        category=PhaseCategory.MANDATORY,
        duration_ms=10.0,
    )

    with pytest.raises(ValueError, match="total_ms"):
        JobTimingReport(
            job_id="job-1",
            total_ms=9.0,
            mandatory_ms=10.0,
            optional_ms=0.0,
            phases=(phase,),
            degraded=False,
        )


def test_job_timing_report_to_dict_round_trip() -> None:
    phases = (
        PhaseTiming(
            phase="perception",
            category=PhaseCategory.MANDATORY,
            duration_ms=10.0,
            detail={"files": 10},
        ),
        PhaseTiming(
            phase="planner",
            category=PhaseCategory.OPTIONAL,
            duration_ms=5.0,
            detail={"rollouts": 8},
        ),
    )
    report = JobTimingReport(
        job_id="job-round-trip",
        total_ms=15.0,
        mandatory_ms=10.0,
        optional_ms=5.0,
        phases=phases,
        degraded=True,
    )

    assert _report_from_dict(report.to_dict()) == report


def test_optional_budget_under_limit_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 0.010))
    collector = TimingCollector()

    with collector.phase("planner", PhaseCategory.OPTIONAL):
        pass

    assert collector.check_optional_budget(11.0) is True
    assert collector.build_report("job-1").degraded is False


def test_optional_budget_equal_to_limit_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 0.010))
    collector = TimingCollector()

    with collector.phase("planner", PhaseCategory.OPTIONAL):
        pass

    assert collector.check_optional_budget(10.0) is True
    assert collector.build_report("job-1").degraded is False


def test_optional_budget_over_limit_marks_report_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 0.011))
    collector = TimingCollector()

    with collector.phase("planner", PhaseCategory.OPTIONAL):
        pass

    assert collector.check_optional_budget(10.0) is False
    assert collector.build_report("job-1").degraded is True


def test_degraded_state_is_sticky(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 0.020))
    collector = TimingCollector()

    with collector.phase("planner", PhaseCategory.OPTIONAL):
        pass

    assert collector.check_optional_budget(10.0) is False
    assert collector.check_optional_budget(100.0) is True
    assert collector.build_report("job-1").degraded is True


def test_mandatory_time_does_not_consume_optional_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clock(monkeypatch, (0.0, 5.0))
    collector = TimingCollector()

    with collector.phase("validator", PhaseCategory.MANDATORY):
        pass

    assert collector.check_optional_budget(0.0) is True
    assert collector.build_report("job-1").degraded is False


@pytest.mark.parametrize(
    "time_budget_ms",
    [-1.0, float("inf"), float("nan")],
)
def test_optional_budget_rejects_invalid_values(
    time_budget_ms: float,
) -> None:
    collector = TimingCollector()

    with pytest.raises(ValueError, match="finite, non-negative"):
        collector.check_optional_budget(time_budget_ms)


def test_empty_collector_builds_zero_report() -> None:
    report = TimingCollector().build_report("empty-job")

    assert report == JobTimingReport(
        job_id="empty-job",
        total_ms=0.0,
        mandatory_ms=0.0,
        optional_ms=0.0,
        phases=(),
        degraded=False,
    )


def test_phase_method_rejects_empty_phase_name() -> None:
    collector = TimingCollector()

    with pytest.raises(ValueError, match="non-empty"):
        collector.phase(" ", PhaseCategory.MANDATORY)
