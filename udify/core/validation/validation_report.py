"""Validation report contracts for verified execution (U2-VERIFIED-EXECUTION).

A ValidationReport records the outcome of applying a patch and probing the
staged game. ``PASSED`` requires the process to exit cleanly, no unhandled
runtime exceptions, and every semantic assertion to have a trusted observed
value that passes. "launched successfully" is NOT the same as "validated".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ValidationStatus(StrEnum):
    """Outcome of a validation attempt."""

    PASSED = "PASSED"
    FAILED_RUNTIME = "FAILED_RUNTIME"
    FAILED_ASSERTION = "FAILED_ASSERTION"
    FAILED_CRASH = "FAILED_CRASH"
    SKIPPED = "SKIPPED"


class EngineCoverage(StrEnum):
    """How deeply an engine supports automated validation.

    Honesty grading (U2 research): only Godot 4 is NATIVE_HEADLESS.
    RPGMV/NW.js is AUTOMATED_NON_HEADLESS (no official headless promise).
    Unity is INSTRUMENTED_PLAYER_ONLY (needs a pre-embedded probe).
    Commercial un-instrumented binaries are UNVERIFIABLE.
    """

    NATIVE_HEADLESS = "NATIVE_HEADLESS"
    AUTOMATED_NON_HEADLESS = "AUTOMATED_NON_HEADLESS"
    INSTRUMENTED_ONLY = "INSTRUMENTED_ONLY"
    UNVERIFIABLE = "UNVERIFIABLE"


class ValidationErrorKind(StrEnum):
    """Where a validation error originated."""

    CRASH = "CRASH"
    RUNTIME = "RUNTIME"
    SILENT = "SILENT"


@dataclass(frozen=True, slots=True)
class AssertionResult:
    """One semantic assertion with its trusted observed value."""

    name: str
    expected: str
    observed: str | None
    passed: bool
    evidence: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class ValidationError:
    """A captured error during execution validation."""

    kind: ValidationErrorKind
    message: str
    source: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind.value, "message": self.message, "source": self.source}


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Final outcome of an execution validation attempt."""

    job_id: str
    status: ValidationStatus
    engine_coverage: EngineCoverage
    assertions: tuple[AssertionResult, ...] = ()
    errors: tuple[ValidationError, ...] = ()
    duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "engine_coverage": self.engine_coverage.value,
            "assertions": [a.to_dict() for a in self.assertions],
            "errors": [e.to_dict() for e in self.errors],
            "duration_ms": self.duration_ms,
        }
