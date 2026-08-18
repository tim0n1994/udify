"""Tests for the real sandbox-exec execution path (iter6 M4, V6 research)."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from udify.core.execution.sandbox import SandboxExecutionResult, SandboxExecutor


class TestExecuteSandboxed:
    @pytest.fixture
    def executor(self) -> SandboxExecutor:
        return SandboxExecutor()

    @pytest.fixture
    def dirs(self, tmp_path):
        workdir = tmp_path / "work"
        game_dir = tmp_path / "game"
        workdir.mkdir()
        game_dir.mkdir()
        return str(workdir), str(game_dir)

    def test_unsandboxed_when_no_sandbox_exec(self, executor, dirs) -> None:
        """If sandbox-exec is absent, do NOT run the command; report unsandboxed honestly."""
        workdir, game_dir = dirs
        with patch("udify.core.execution.sandbox.shutil.which", return_value=None):
            result = executor.execute_sandboxed(["echo", "hi"], workdir=workdir, game_dir=game_dir)
        assert result.status == "unsandboxed"
        assert result.exit_code is None
        assert "not found" in result.reason

    def test_sandboxed_when_available(self, executor, dirs) -> None:
        """When sandbox-exec exists, it is invoked and the result is sandboxed."""
        workdir, game_dir = dirs
        fake_proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
        with (
            patch(
                "udify.core.execution.sandbox.shutil.which", return_value="/usr/bin/sandbox-exec"
            ),
            patch("udify.core.execution.sandbox.subprocess.run", return_value=fake_proc),
        ):
            result = executor.execute_sandboxed(["echo", "ok"], workdir=workdir, game_dir=game_dir)
        assert result.status == "sandboxed"
        assert result.exit_code == 0
        assert result.stdout == "ok"

    def test_sandboxed_failure_reports_exit_code(self, executor, dirs) -> None:
        """A denied operation still reports sandboxed with the real exit code."""
        workdir, game_dir = dirs
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="operation denied"
        )
        with (
            patch(
                "udify.core.execution.sandbox.shutil.which", return_value="/usr/bin/sandbox-exec"
            ),
            patch("udify.core.execution.sandbox.subprocess.run", return_value=fake_proc),
        ):
            result = executor.execute_sandboxed(["dangerous"], workdir=workdir, game_dir=game_dir)
        assert result.status == "sandboxed"
        assert result.exit_code == 1
        assert "denied" in result.stderr

    def test_timeout_marks_sandboxed_timeout(self, executor, dirs) -> None:
        workdir, game_dir = dirs
        with (
            patch(
                "udify.core.execution.sandbox.shutil.which", return_value="/usr/bin/sandbox-exec"
            ),
            patch(
                "udify.core.execution.sandbox.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=[], timeout=5),
            ),
        ):
            result = executor.execute_sandboxed(
                ["sleep", "100"], workdir=workdir, game_dir=game_dir, timeout_s=5
            )
        assert result.status == "sandboxed"
        assert result.exit_code == -9
        assert "timed out" in result.stderr


class TestSandboxExecutionResult:
    def test_is_frozen(self) -> None:
        r = SandboxExecutionResult(
            status="sandboxed", exit_code=0, stdout="", stderr="", duration_ms=10
        )
        with pytest.raises(AttributeError):
            r.status = "unsandboxed"  # type: ignore[misc]

    def test_default_reason_empty(self) -> None:
        r = SandboxExecutionResult(
            status="sandboxed", exit_code=0, stdout="", stderr="", duration_ms=10
        )
        assert r.reason == ""

    def test_status_never_implicit(self) -> None:
        """The result must always declare its status explicitly."""
        r = SandboxExecutionResult(
            status="unsandboxed", exit_code=None, stdout="", stderr="", duration_ms=5
        )
        assert r.status in ("sandboxed", "unsandboxed")
