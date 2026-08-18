"""Static script analysis for dangerous API usage (U4-SANDBOX-REAL PR1).

This is the FIRST layer of defense: it statically rejects known-dangerous APIs
before any sandboxed execution. It is NOT a sandbox — unknown or obfuscated
calls still need a runtime sandbox (seatbelt/gVisor) as the second layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


# Real dangerous API catalogs (U4 research, grounded in real docs).
LUA_DANGEROUS = {
    "os.execute": Severity.CRITICAL,
    "os.exit": Severity.HIGH,
    "os.getenv": Severity.MEDIUM,
    "os.remove": Severity.CRITICAL,
    "os.rename": Severity.HIGH,
    "io.popen": Severity.CRITICAL,
    "io.open": Severity.HIGH,
    "loadstring": Severity.CRITICAL,
    "load": Severity.CRITICAL,
    "dofile": Severity.HIGH,
    "require": Severity.HIGH,
    "ffi.C": Severity.CRITICAL,
    "debug.getinfo": Severity.MEDIUM,
    "debug.sethook": Severity.MEDIUM,
}

JS_DANGEROUS = {
    "require('child_process')": Severity.CRITICAL,
    "require('fs')": Severity.CRITICAL,
    'require("child_process")': Severity.CRITICAL,
    'require("fs")': Severity.CRITICAL,
    "child_process.exec": Severity.CRITICAL,
    "child_process.execSync": Severity.CRITICAL,
    "fs.writeFileSync": Severity.CRITICAL,
    "fs.readFile": Severity.HIGH,
    "eval(": Severity.CRITICAL,
    "Function(": Severity.CRITICAL,
    "process.exit": Severity.HIGH,
    "process.env": Severity.MEDIUM,
    "setTimeout": Severity.MEDIUM,
}


@dataclass(frozen=True, slots=True)
class BlockedApiCall:
    name: str
    severity: Severity
    line: int | None
    suggestion: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "severity": self.severity.value,
            "line": self.line,
            "suggestion": self.suggestion,
        }


@dataclass(frozen=True, slots=True)
class ScriptAnalysis:
    language: str
    blocked_apis: tuple[BlockedApiCall, ...]
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "blocked_apis": [b.to_dict() for b in self.blocked_apis],
            "passed": self.passed,
        }


def _find_in_lines(pattern: str, code: str) -> list[tuple[int, str]]:
    """Return (line_number, matched_text) for each occurrence."""
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(code.splitlines(), start=1):
        if pattern in line:
            hits.append((i, pattern))
    return hits


def analyze_script(language: str, code: str) -> ScriptAnalysis:
    """Analyze a script for dangerous API usage.

    Args:
        language: ``"lua"`` or ``"js"``.
        code: The script source.

    Returns:
        A ScriptAnalysis with every detected dangerous call and ``passed=False``
        if any were found. This is static pattern matching, not a full sandbox.
    """
    lang = language.lower()
    catalog = LUA_DANGEROUS if lang == "lua" else JS_DANGEROUS if lang == "js" else {}
    blocked: list[BlockedApiCall] = []
    for api, severity in catalog.items():
        for line_no, _ in _find_in_lines(api, code):
            blocked.append(
                BlockedApiCall(
                    name=api,
                    severity=severity,
                    line=line_no,
                    suggestion=f"Avoid {api}; it can escape the sandbox. Use a safe equivalent or request review.",
                )
            )
    blocked.sort(key=lambda b: (b.line if b.line else 0, b.name))
    return ScriptAnalysis(language=lang, blocked_apis=tuple(blocked), passed=len(blocked) == 0)
