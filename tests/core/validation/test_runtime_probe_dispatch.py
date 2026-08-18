"""Test: HeadlessRuntimeProbe engine dispatch (U2 PR2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from udify.core.validation.runtime_probe import HeadlessRuntimeProbe


def test_godot_dispatch_without_binary_is_honest_skip():
    probe = HeadlessRuntimeProbe()
    with patch("udify.core.validation.godot_probe.shutil.which", return_value=None):
        report = probe.run_by_engine("godot", Path("/tmp/x"), Path("/tmp/p.gd"), job_id="j")
    assert report.passed is False
    assert report.engine_coverage == "NATIVE_HEADLESS"


def test_unknown_engine_is_unverifiable():
    probe = HeadlessRuntimeProbe()
    report = probe.run_by_engine("unity", Path("/tmp/x"), Path("/tmp/p.gd"), job_id="j")
    assert report.passed is False
    assert report.engine_coverage == "UNVERIFIABLE"


def test_rpgmv_is_automated_non_headless():
    probe = HeadlessRuntimeProbe()
    report = probe.run_by_engine("rpgmv", Path("/tmp/x"), Path("/tmp/p.gd"), job_id="j")
    assert report.engine_coverage == "AUTOMATED_NON_HEADLESS"
    assert report.passed is False  # honest: not a synthetic PASS
