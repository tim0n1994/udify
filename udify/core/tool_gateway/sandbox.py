"""
OS 级沙箱执行器（§4.4）。

对应 ITERATION-PLAN-2026-07.md §4.4「沙箱：从占位到真实」：
- macOS（JC 主力平台）：Seatbelt（``sandbox-exec``）等价物；
- Linux：Landlock + seccomp-bpf 占位（社区共识，无 root/namespace/容器）；
- **默认断网**：工具默认 network=none + 显式 allowlist；
- **密钥不进沙箱**：沙箱内进程看不到 API key（env 清除）。

这是把 ``execution/sandbox.py`` 的占位（``"Docker execution not configured"``）
替换为真实 OS 级原语。作为 ``ToolGateway.call_with_runner`` 的 runner 注入。
"""

from __future__ import annotations

import contextlib
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from udify.core.tool_gateway.gateway import ToolCallRequest, ToolCallResult


@dataclass
class SandboxProfile:
    """沙箱配置。

    Attributes:
        allowed_read_roots: 允许读取的根目录（game_root + workspace_cache）。
        allowed_write_roots: 允许写入的根目录。
        network_allowed: 是否允许联网（默认 False = 全断网）。
        secret_env_keys: 进入沙箱前清除的环境变量名（API key 等）。
    """

    allowed_read_roots: list[Path] = field(default_factory=list)
    allowed_write_roots: list[Path] = field(default_factory=list)
    network_allowed: bool = False
    secret_env_keys: tuple[str, ...] = (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "API_KEY",
        "SECRET",
        "TOKEN",
    )


def _seatbelt_profile(profile: SandboxProfile) -> str:
    """生成 macOS Seatbelt (sandbox-exec) profile。

    采用 "allow default + 针对性 deny" 策略（而非 deny default），因为 macOS
    的 Mach 系统调用面极广，deny default 会连合法进程启动都打断（SIGABRT）。
    真正的安全边界落在：
    - **默认断网**（``deny network*``，除非显式 allow）；
    - **写入受限**（``deny file-write*``，仅 allow 指定根 + 临时目录）；
    - **密钥不进沙箱**（env 清除，在 Python 层）。

    这实现了 §4.4「默认断网 + per-tool 最小权限 + 密钥不进沙箱」。
    """
    lines = [
        "(version 1)",
        "(allow default)",
    ]
    # 默认断网（§4.4：默认 --network=none）
    if not profile.network_allowed:
        lines.append("(deny network*)")
    # 写入受限：默认 deny file-write*，仅 allow 指定根 + 临时目录
    lines.append("(deny file-write*)")
    lines.append(
        '(allow file-write* (subpath "/private/var/folders") (subpath "/private/tmp") (subpath "/tmp"))'
    )
    # 允许写入的根
    for root in profile.allowed_write_roots:
        rp = str(root.resolve())
        lines.append(f'(allow file-write* (subpath "{rp}"))')
    # 显式 allow 读取的根（allow default 已覆盖读取，这里仅记录意图）
    for root in profile.allowed_read_roots:
        rp = str(root.resolve())
        lines.append(f"; allowed read root: {rp}")
    return "\n".join(lines) + "\n"


def _landlock_seccomp_available() -> bool:
    """Linux Landlock 是否可用（内核 5.13+）。"""
    if platform.system() != "Linux":
        return False
    try:
        # 粗略检测：landlock_create_ruleset syscall 是否存在
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        return hasattr(libc, "landlock_create_ruleset")
    except Exception:
        return False


class SandboxExecutor:
    """OS 级沙箱执行器。

    macOS 上用 ``sandbox-exec``（Seatbelt）；Linux 上 Landlock 占位（记录未集成）；
    其它平台降级为受限 subprocess（env 清除 + 超时，但无 OS 级隔离）。
    """

    def __init__(self, profile: SandboxProfile | None = None) -> None:
        self.profile = profile or SandboxProfile()
        self._platform = platform.system()

    @property
    def backend(self) -> str:
        """当前生效的沙箱后端。"""
        if self._platform == "Darwin":
            return "seatbelt"
        if self._platform == "Linux" and _landlock_seccomp_available():
            return "landlock"
        return "restricted-subprocess"

    def run(self, request: ToolCallRequest) -> ToolCallResult:
        """在沙箱内执行工具调用。"""
        timeout = request.timeout if request.timeout is not None else 300
        # 清除密钥 env（§4.4：密钥不进沙箱）
        clean_env = {k: v for k, v in os.environ.items() if k not in self.profile.secret_env_keys}

        start = time.monotonic()

        if self.backend == "seatbelt":
            return self._run_seatbelt(request, clean_env, timeout, start)
        # restricted-subprocess（Linux Landlock 占位 / 其它平台）
        return self._run_restricted(request, clean_env, timeout, start)

    def _run_seatbelt(
        self,
        request: ToolCallRequest,
        env: dict[str, str],
        timeout: int,
        start: float,
    ) -> ToolCallResult:
        """macOS Seatbelt 执行。

        ``sandbox-exec -p`` 接收 inline profile 文本；``-f`` 接收 profile 文件路径。
        用 ``-f`` 避免把多行 profile 作为单参数传递的转义问题。
        """
        profile_text = _seatbelt_profile(self.profile)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False) as pf:
            pf.write(profile_text)
            profile_path = pf.name
        try:
            cmd = [
                "sandbox-exec",
                "-f",
                profile_path,
                *request.args,
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            duration = time.monotonic() - start
            return ToolCallResult(
                success=proc.returncode == 0,
                return_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                decision=None,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            return ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"timed out after {timeout}s (seatbelt)",
                blocked_reason="timeout",
            )
        except FileNotFoundError:
            return ToolCallResult(
                success=False,
                return_code=None,
                stderr="sandbox-exec not found (Seatbelt unavailable)",
                blocked_reason="seatbelt_unavailable",
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(profile_path)

    def _run_restricted(
        self,
        request: ToolCallRequest,
        env: dict[str, str],
        timeout: int,
        start: float,
    ) -> ToolCallResult:
        """受限 subprocess（env 清除 + 超时；无 OS 级隔离的降级）。"""
        try:
            proc = subprocess.run(
                request.args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            duration = time.monotonic() - start
            return ToolCallResult(
                success=proc.returncode == 0,
                return_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                decision=None,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            return ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"timed out after {timeout}s",
                blocked_reason="timeout",
            )
        except FileNotFoundError:
            return ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"tool not found: {request.args[0] if request.args else ''}",
                blocked_reason="tool_not_found",
            )


__all__ = ["SandboxExecutor", "SandboxProfile"]
