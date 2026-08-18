"""Local monotonic timers for Udify pipeline phase measurements."""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from threading import Lock
from types import TracebackType
from typing import Literal

from udify.core.infrastructure.timing import (
    JobTimingReport,
    PhaseCategory,
    PhaseTiming,
)


class PhaseTimer:
    """One-shot context manager that records a pipeline phase duration.

    Instances are created through :meth:`TimingCollector.phase`.
    ``time.perf_counter`` is used so measurements are not affected by
    wall-clock adjustments.
    """

    __slots__ = (
        "_category",
        "_collector",
        "_detail",
        "_finished",
        "_phase",
        "_started_at",
    )

    def __init__(
        self,
        collector: TimingCollector,
        phase: str,
        category: PhaseCategory,
        detail: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize a one-shot phase timer.

        Args:
            collector: Collector that receives the completed timing.
            phase: Stable phase name.
            category: Mandatory or optional phase classification.
            detail: Optional phase-specific measurement metadata.
        """
        if not phase.strip():
            raise ValueError("phase must be a non-empty string")

        self._collector = collector
        self._phase = phase
        self._category = category
        self._detail = dict(detail) if detail is not None else {}
        self._started_at: float | None = None
        self._finished = False

    def __enter__(self) -> PhaseTimer:
        """Start measuring the phase.

        Returns:
            This phase timer.

        Raises:
            RuntimeError: If the one-shot timer was already entered.
        """
        if self._started_at is not None or self._finished:
            raise RuntimeError("PhaseTimer instances may only be entered once")

        self._started_at = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Stop measuring and record the phase without suppressing errors.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc_value: Exception raised inside the context, if any.
            traceback: Exception traceback, if any.

        Returns:
            ``False`` so exceptions from the measured phase propagate.

        Raises:
            RuntimeError: If called before the timer was entered.
        """
        del exc_type, exc_value, traceback

        if self._started_at is None:
            raise RuntimeError("PhaseTimer exited before it was entered")

        ended_at = time.perf_counter()
        duration_seconds = ended_at - self._started_at
        if duration_seconds < 0.0:
            raise RuntimeError("time.perf_counter moved backwards")

        self._collector._record(
            PhaseTiming(
                phase=self._phase,
                category=self._category,
                duration_ms=duration_seconds * 1_000.0,
                detail=self._detail,
            )
        )
        self._started_at = None
        self._finished = True
        return False


class TimingCollector:
    """Thread-safe accumulator for phase timings belonging to one job."""

    __slots__ = ("_degraded", "_lock", "_phases")

    def __init__(self) -> None:
        """Initialize an empty timing collector."""
        self._phases: list[PhaseTiming] = []
        self._degraded = False
        self._lock = Lock()

    def phase(
        self,
        phase: str,
        category: PhaseCategory,
        detail: Mapping[str, object] | None = None,
    ) -> PhaseTimer:
        """Create a context manager for one measured phase.

        Args:
            phase: Stable phase name.
            category: Mandatory or optional phase classification.
            detail: Optional phase-specific measurement metadata.

        Returns:
            A one-shot context manager that records elapsed time on exit.
        """
        return PhaseTimer(
            collector=self,
            phase=phase,
            category=category,
            detail=detail,
        )

    def check_optional_budget(self, time_budget_ms: float) -> bool:
        """Check accumulated optional work against a latency budget.

        Exceeding the budget marks the collector as degraded. The degraded
        state is sticky for the remainder of the collector lifetime. No
        exception is raised for budget exhaustion because the caller owns
        the actual degradation decision.

        Args:
            time_budget_ms: Maximum permitted accumulated optional duration.

        Returns:
            ``True`` when optional duration is within budget; otherwise
            ``False``.

        Raises:
            ValueError: If the supplied budget is negative or non-finite.
        """
        if not math.isfinite(time_budget_ms) or time_budget_ms < 0.0:
            raise ValueError("time_budget_ms must be a finite, non-negative value")

        with self._lock:
            optional_ms = sum(
                phase.duration_ms
                for phase in self._phases
                if phase.category is PhaseCategory.OPTIONAL
            )
            within_budget = optional_ms <= time_budget_ms
            if not within_budget:
                self._degraded = True
            return within_budget

    def build_report(self, job_id: str) -> JobTimingReport:
        """Build an immutable point-in-time report for the collected phases.

        Args:
            job_id: Identifier of the measured job.

        Returns:
            An immutable report containing ordered phase timings and totals.
        """
        with self._lock:
            phases = tuple(self._phases)
            degraded = self._degraded

        mandatory_ms = sum(
            phase.duration_ms for phase in phases if phase.category is PhaseCategory.MANDATORY
        )
        optional_ms = sum(
            phase.duration_ms for phase in phases if phase.category is PhaseCategory.OPTIONAL
        )
        total_ms = sum(phase.duration_ms for phase in phases)

        return JobTimingReport(
            job_id=job_id,
            total_ms=total_ms,
            mandatory_ms=mandatory_ms,
            optional_ms=optional_ms,
            phases=phases,
            degraded=degraded,
        )

    def _record(self, timing: PhaseTiming) -> None:
        """Append a completed phase timing under the collector lock."""
        with self._lock:
            self._phases.append(timing)
