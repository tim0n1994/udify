"""Immutable timing models for Udify pipeline phase observability."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class PhaseCategory(StrEnum):
    """Classification used to separate required and degradable work."""

    MANDATORY = "mandatory"
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class PhaseTiming:
    """Measured duration and metadata for one pipeline phase.

    Attributes:
        phase: Stable phase name, such as ``"perception"``.
        category: Whether the phase is mandatory or optional.
        duration_ms: Measured elapsed time in milliseconds.
        detail: Immutable phase-specific measurement metadata.
    """

    phase: str
    category: PhaseCategory
    duration_ms: float
    detail: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize the immutable timing record."""
        if not self.phase.strip():
            raise ValueError("phase must be a non-empty string")
        if not math.isfinite(self.duration_ms) or self.duration_ms < 0.0:
            raise ValueError("duration_ms must be a finite, non-negative value")

        object.__setattr__(
            self,
            "detail",
            MappingProxyType(dict(self.detail)),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible copy of this phase timing.

        Returns:
            A dictionary containing the phase timing fields.
        """
        return {
            "phase": self.phase,
            "category": self.category.value,
            "duration_ms": self.duration_ms,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True, slots=True)
class JobTimingReport:
    """Immutable aggregate timing report for one Udify job.

    Attributes:
        job_id: Identifier of the measured job.
        total_ms: Sum of all measured phase durations.
        mandatory_ms: Sum of mandatory phase durations.
        optional_ms: Sum of optional phase durations.
        phases: Ordered phase timing records.
        degraded: Whether an optional latency budget was exceeded.
    """

    job_id: str
    total_ms: float
    mandatory_ms: float
    optional_ms: float
    phases: tuple[PhaseTiming, ...]
    degraded: bool

    def __post_init__(self) -> None:
        """Validate aggregate values against the supplied phase records."""
        if not self.job_id.strip():
            raise ValueError("job_id must be a non-empty string")

        for field_name, value in (
            ("total_ms", self.total_ms),
            ("mandatory_ms", self.mandatory_ms),
            ("optional_ms", self.optional_ms),
        ):
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{field_name} must be a finite, non-negative value")

        expected_total = sum(phase.duration_ms for phase in self.phases)
        expected_mandatory = sum(
            phase.duration_ms for phase in self.phases if phase.category is PhaseCategory.MANDATORY
        )
        expected_optional = sum(
            phase.duration_ms for phase in self.phases if phase.category is PhaseCategory.OPTIONAL
        )

        if not math.isclose(
            self.total_ms,
            expected_total,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("total_ms does not equal the sum of phase durations")
        if not math.isclose(
            self.mandatory_ms,
            expected_mandatory,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("mandatory_ms does not equal the sum of mandatory phases")
        if not math.isclose(
            self.optional_ms,
            expected_optional,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError("optional_ms does not equal the sum of optional phases")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible copy of this job timing report.

        Returns:
            A dictionary containing aggregate values and phase records.
        """
        return {
            "job_id": self.job_id,
            "total_ms": self.total_ms,
            "mandatory_ms": self.mandatory_ms,
            "optional_ms": self.optional_ms,
            "phases": [phase.to_dict() for phase in self.phases],
            "degraded": self.degraded,
        }
