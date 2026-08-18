"""Godot 4 native headless probe (U2-VERIFIED-EXECUTION PR1).

Godot 4 is the cleanest engine for verified execution: it ships a real
``--headless`` mode (dummy display + dummy audio driver) with ``--quit-after``,
``--script`` (GDScript entrypoint), and ``--log-file``. This module launches a
staged Godot project headlessly, runs a probe script that emits JSON
assertions, and produces a ``ValidationReport`` graded ``NATIVE_HEADLESS``.

Three-layer judgement (U2 research):
  1. exit code != 0                 -> FAILED_CRASH
  2. stderr contains engine errors -> FAILED_RUNTIME
  3. any assertion failed          -> FAILED_ASSERTION
  otherwise                        -> PASSED

If the ``godot`` binary is absent we return ``SKIPPED`` honestly — never a
synthetic PASS.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from udify.core.validation.validation_report import (
    AssertionResult,
    EngineCoverage,
    ValidationError,
    ValidationErrorKind,
    ValidationReport,
    ValidationStatus,
)

_GODOT_BINARIES = ("godot", "godot4")
# Godot/runtime error markers seen in stderr.
_RUNTIME_ERROR_MARKERS = (
    "SCRIPT ERROR",
    "ERROR:",
    "USER SCRIPT ERROR",
    "Parse Error",
    "Fatal",
)


def _has_godot_binary(godot_bin: str | None) -> str | None:
    if godot_bin and shutil.which(godot_bin):
        return godot_bin
    for candidate in _GODOT_BINARIES:
        if shutil.which(candidate):
            return candidate
    return None


def _contains_runtime_error(text: str) -> bool:
    return any(marker in text for marker in _RUNTIME_ERROR_MARKERS)


def _load_assertions(path: Path) -> tuple[AssertionResult, ...]:
    """Parse the probe's JSON output into AssertionResult records."""
    if not path.exists():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ()
    raw = payload.get("assertions") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        return ()
    results: list[AssertionResult] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        results.append(
            AssertionResult(
                name=str(item.get("name", "")),
                expected=str(item.get("expected", "")),
                observed=str(item.get("observed")) if item.get("observed") is not None else None,
                passed=bool(item.get("passed", False)),
                evidence=str(item.get("evidence", "")),
            )
        )
    return tuple(results)


def run_godot_headless(
    staging_dir: Path,
    probe_script: Path,
    *,
    godot_bin: str | None = None,
    quit_after: int = 120,
    timeout_s: float = 60.0,
    job_id: str = "",
) -> ValidationReport:
    """Run a staged Godot project headlessly and judge the outcome.

    Args:
        staging_dir: The staged project directory (--path).
        probe_script: A ``.gd`` SceneTree/MainLoop script that emits JSON.
        godot_bin: Override the Godot binary name; auto-detected if None.
        quit_after: ``--quit-after`` value (main-loop iterations, NOT seconds).
        timeout_s: Wall-clock timeout for the subprocess.
        job_id: Job identifier for the report.

    Returns:
        A ValidationReport. ``NATIVE_HEADLESS`` coverage. ``SKIPPED`` if the
        Godot binary is unavailable — never a synthetic PASS.
    """
    resolved = _has_godot_binary(godot_bin)
    if resolved is None:
        return ValidationReport(
            job_id=job_id,
            status=ValidationStatus.SKIPPED,
            engine_coverage=EngineCoverage.NATIVE_HEADLESS,
            errors=(
                ValidationError(
                    kind=ValidationErrorKind.RUNTIME,
                    message="godot binary not found on PATH; cannot run headless validation",
                    source="probe",
                ),
            ),
        )

    log_file = staging_dir / ".udify-godot.log"
    assertions_file = staging_dir / ".udify-assertions.json"
    cmd = [
        resolved,
        "--headless",
        "--path",
        str(staging_dir),
        "--script",
        str(probe_script),
        "--quit-after",
        str(quit_after),
        "--log-file",
        str(log_file),
    ]
    try:
        completed = subprocess.run(  # noqa: S603 — trusted local binary, args are explicit
            cmd,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return ValidationReport(
            job_id=job_id,
            status=ValidationStatus.FAILED_CRASH,
            engine_coverage=EngineCoverage.NATIVE_HEADLESS,
            errors=(
                ValidationError(
                    kind=ValidationErrorKind.CRASH,
                    message=f"godot headless timed out after {timeout_s}s",
                    source="probe",
                ),
            ),
        )

    stderr = completed.stderr or ""
    assertions = _load_assertions(assertions_file)
    errors: list[ValidationError] = []

    # Layer 1: crash (non-zero exit).
    if completed.returncode != 0:
        errors.append(
            ValidationError(
                kind=ValidationErrorKind.CRASH,
                message=f"godot exited with code {completed.returncode}",
                source="exit_code",
            )
        )
        status = ValidationStatus.FAILED_CRASH
    # Layer 2: runtime error in stderr.
    elif _contains_runtime_error(stderr):
        errors.append(
            ValidationError(
                kind=ValidationErrorKind.RUNTIME,
                message="runtime error detected in stderr",
                source="stderr",
            )
        )
        status = ValidationStatus.FAILED_RUNTIME
    # Layer 3: assertion failure.
    elif any(not a.passed for a in assertions):
        status = ValidationStatus.FAILED_ASSERTION
    else:
        status = ValidationStatus.PASSED

    return ValidationReport(
        job_id=job_id,
        status=status,
        engine_coverage=EngineCoverage.NATIVE_HEADLESS,
        assertions=assertions,
        errors=tuple(errors),
        duration_ms=0,
    )
