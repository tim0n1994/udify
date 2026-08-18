"""Test: ScriptAnalyzer wired into validate_script_safety (U4 PR2 two-layer defense)."""

from __future__ import annotations

from udify.core.execution.sandbox import SandboxExecutor


def test_dangerous_lua_caught_by_both_layers():
    se = SandboxExecutor()
    report = se.validate_script_safety('os.execute("rm -rf /")', "lua")
    assert not report.is_safe
    # Both inline regex and script_analyzer should flag it.
    types = [v.get("type") for v in report.vulnerabilities]
    assert "dangerous_pattern" in types
    assert "script_analyzer" in types


def test_safe_code_passes_both_layers():
    se = SandboxExecutor()
    report = se.validate_script_safety("local x = 1 + 2", "lua")
    assert report.is_safe


def test_js_dangerous_api_caught_by_analyzer_layer():
    se = SandboxExecutor()
    # The inline regex only covers lua+dsl, so JS danger is caught by script_analyzer.
    report = se.validate_script_safety("require('child_process')", "js")
    assert not report.is_safe
