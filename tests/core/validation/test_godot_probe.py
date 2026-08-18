"""Tests for Godot headless probe (U2-VERIFIED-EXECUTION PR1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from udify.core.validation.godot_probe import run_godot_headless
from udify.core.validation.validation_report import (
    EngineCoverage,
    ValidationStatus,
)


def test_skipped_when_godot_binary_absend(monkeypatch):
    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: None)
    report = run_godot_headless(Path("/tmp/fake"), Path("/tmp/probe.gd"), job_id="j1")
    assert report.status is ValidationStatus.SKIPPED
    assert report.engine_coverage is EngineCoverage.NATIVE_HEADLESS


def test_passed_requires_clean_exit_no_errors_all_assertions(monkeypatch, tmp_path):
    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: "godot")
    monkeypatch.setattr("udify.core.validation.godot_probe._load_assertions", lambda p: ())
    fake = MagicMock(returncode=0, stderr="", stdout="")
    monkeypatch.setattr("udify.core.validation.godot_probe.subprocess.run", lambda *a, **k: fake)
    report = run_godot_headless(tmp_path, tmp_path / "probe.gd", job_id="j2")
    assert report.status is ValidationStatus.PASSED
    assert report.engine_coverage is EngineCoverage.NATIVE_HEADLESS


def test_failed_crash_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: "godot")
    monkeypatch.setattr("udify.core.validation.godot_probe._load_assertions", lambda p: ())
    fake = MagicMock(returncode=1, stderr="", stdout="")
    monkeypatch.setattr("udify.core.validation.godot_probe.subprocess.run", lambda *a, **k: fake)
    report = run_godot_headless(tmp_path, tmp_path / "probe.gd", job_id="j3")
    assert report.status is ValidationStatus.FAILED_CRASH


def test_failed_runtime_on_stderr_error(monkeypatch, tmp_path):
    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: "godot")
    monkeypatch.setattr("udify.core.validation.godot_probe._load_assertions", lambda p: ())
    fake = MagicMock(returncode=0, stderr="SCRIPT ERROR: bad", stdout="")
    monkeypatch.setattr("udify.core.validation.godot_probe.subprocess.run", lambda *a, **k: fake)
    report = run_godot_headless(tmp_path, tmp_path / "probe.gd", job_id="j4")
    assert report.status is ValidationStatus.FAILED_RUNTIME


def test_failed_assertion_when_probe_reports_failure(monkeypatch, tmp_path):
    from udify.core.validation.validation_report import AssertionResult

    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: "godot")
    bad = AssertionResult(
        name="hp", expected="200", observed="100", passed=False, evidence="mismatch"
    )
    monkeypatch.setattr("udify.core.validation.godot_probe._load_assertions", lambda p: (bad,))
    fake = MagicMock(returncode=0, stderr="", stdout="")
    monkeypatch.setattr("udify.core.validation.godot_probe.subprocess.run", lambda *a, **k: fake)
    report = run_godot_headless(tmp_path, tmp_path / "probe.gd", job_id="j5")
    assert report.status is ValidationStatus.FAILED_ASSERTION


def test_timeout_produces_failed_crash(monkeypatch, tmp_path):
    import subprocess as sp

    monkeypatch.setattr("udify.core.validation.godot_probe.shutil.which", lambda _: "godot")

    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd="godot", timeout=1)

    monkeypatch.setattr("udify.core.validation.godot_probe.subprocess.run", boom)
    report = run_godot_headless(tmp_path, tmp_path / "probe.gd", timeout_s=1, job_id="j6")
    assert report.status is ValidationStatus.FAILED_CRASH


def test_report_is_frozen():
    from udify.core.validation.validation_report import ValidationReport

    r = ValidationReport(
        job_id="x", status=ValidationStatus.SKIPPED, engine_coverage=EngineCoverage.NATIVE_HEADLESS
    )
    with pytest.raises(AttributeError):
        r.job_id = "y"  # type: ignore[misc]


def test_report_to_dict_roundtrip():
    from udify.core.validation.validation_report import ValidationReport

    r = ValidationReport(
        job_id="x", status=ValidationStatus.PASSED, engine_coverage=EngineCoverage.NATIVE_HEADLESS
    )
    d = r.to_dict()
    assert d["status"] == "PASSED"
    assert d["engine_coverage"] == "NATIVE_HEADLESS"
