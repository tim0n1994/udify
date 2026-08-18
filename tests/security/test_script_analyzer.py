"""Tests for script static analysis (U4-SANDBOX-REAL PR1)."""

from __future__ import annotations

import pytest

from udify.core.security.script_analyzer import Severity, analyze_script


@pytest.mark.parametrize(
    "code",
    [
        'os.execute("rm -rf /")',
        "os.exit(1)",
        'local f = io.popen("ls")',
        'loadstring("print(1)")()',
        'ffi.C.system("x")',
    ],
)
def test_lua_blocks_critical_apis(code):
    r = analyze_script("lua", code)
    assert not r.passed
    assert any(b.severity in (Severity.CRITICAL, Severity.HIGH) for b in r.blocked_apis)


def test_safe_lua_passes():
    assert analyze_script("lua", "local x = 1 + 2").passed


def test_js_blocks_require_fs():
    r = analyze_script("js", "const fs = require('fs')")
    assert not r.passed
    assert any("fs" in b.name for b in r.blocked_apis)


def test_js_blocks_eval():
    r = analyze_script("js", "eval('alert(1)')")
    assert not r.passed


def test_blocked_calls_have_line_numbers():
    code = "local a = 1\nos.execute('x')\n"
    r = analyze_script("lua", code)
    assert r.blocked_apis[0].line == 2


def test_to_dict_structure():
    r = analyze_script("lua", "os.execute('x')")
    d = r.to_dict()
    assert d["language"] == "lua"
    assert d["passed"] is False
    assert d["blocked_apis"][0]["severity"] == "CRITICAL"


def test_unknown_language_passes():
    assert analyze_script("ruby", "system('rm')").passed
