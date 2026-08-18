"""
Secure Tool Gateway —— 主网关（TOOL-GW-01..06）。

对应 ITERATION-PLAN-2026-07.md §4.3。**所有外部工具调用必须经此唯一入口**
（ADR-v3-003）。流程：

    ToolCallRequest → schema 校验 → policy 决策 → sandbox 分配 → 路径 allowlist
        → 资源配额 + 超时 → 工具执行 → output sanitizer → audit append → ToolCallResult

迁移策略（计划 §4.3）：先让一个真实调用（如 miu2d converter）走 gateway，
验证拦截有效，再逐个搬。本文件提供可执行的网关与拦截点。
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.tool_gateway.audit import ToolAuditChain, ToolCallRecord, now_iso
from udify.core.tool_gateway.lockfile import ToolLockfile
from udify.core.tool_gateway.policy import PolicyDecision, RiskLevel, ToolPolicy


@dataclass
class ToolCallRequest:
    """工具调用请求。"""

    tool_id: str
    capability: str
    args: list[str] = field(default_factory=list)
    job_id: str = ""
    requested_paths: list[Path] = field(default_factory=list)
    timeout: int | None = None
    risk_override: RiskLevel | None = None


@dataclass
class ToolCallResult:
    """工具调用结果。"""

    success: bool
    return_code: int | None
    stdout: str = ""
    stderr: str = ""
    output_artifact: str | None = None  # 截断输出的落盘路径
    blocked_reason: str = ""
    decision: PolicyDecision | None = None
    duration_seconds: float = 0.0


# 输出截断阈值：超过则落盘为 artifact，只保留前 N 字符在 stdout
_MAX_INLINE_OUTPUT = 4096


class ToolGateway:
    """工具网关：所有外部工具调用的唯一入口。"""

    def __init__(
        self,
        policy: ToolPolicy | None = None,
        audit: ToolAuditChain | None = None,
        lockfile: ToolLockfile | None = None,
        artifact_dir: Path | None = None,
    ) -> None:
        self.policy = policy or ToolPolicy()
        self.audit = audit or ToolAuditChain()
        self.lockfile = lockfile or ToolLockfile()
        self.artifact_dir = artifact_dir

    def call(self, request: ToolCallRequest) -> ToolCallResult:
        """执行一次受控工具调用。"""
        # 1. 策略决策（路径 allowlist + 风险 + 超时）
        decision = self.policy.evaluate(
            tool_id=request.tool_id,
            capability=request.capability,
            requested_paths=request.requested_paths or None,
            timeout=request.timeout,
        )

        if not decision.allowed:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason=decision.reason,
                decision=decision,
            )
            self._audit(request, decision, result)
            return result

        # 2. 执行（默认断网：不设 env，进程继承宿主但工具自身不应联网；
        #    沙箱分配由调用方/上层在 R3+ 时注入 runner，见 call_with_runner）
        timeout = (
            request.timeout if request.timeout is not None else self.policy.max_timeout_seconds
        )
        try:
            import time

            start = time.monotonic()
            proc = subprocess.run(
                request.args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""

            # 3. output sanitizer：超大输出截断落盘
            artifact = None
            if len(stdout) > _MAX_INLINE_OUTPUT and self.artifact_dir is not None:
                artifact = self._write_artifact(request, stdout)
                stdout = stdout[:_MAX_INLINE_OUTPUT] + "\n[truncated, see artifact]"

            result = ToolCallResult(
                success=proc.returncode == 0,
                return_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                output_artifact=artifact,
                decision=decision,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            result = ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"timed out after {timeout}s",
                blocked_reason="timeout",
                decision=decision,
            )
        except FileNotFoundError:
            result = ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"tool not found: {request.args[0] if request.args else ''}",
                blocked_reason="tool_not_found",
                decision=decision,
            )

        self._audit(request, decision, result)
        return result

    def call_with_runner(
        self, request: ToolCallRequest, runner: Callable[[ToolCallRequest], ToolCallResult]
    ) -> ToolCallResult:
        """允许上层注入沙箱化 runner（Landlock/Seatbelt/Docker），网关仍负责策略+审计。"""
        decision = self.policy.evaluate(
            tool_id=request.tool_id,
            capability=request.capability,
            requested_paths=request.requested_paths or None,
            timeout=request.timeout,
        )
        if not decision.allowed:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason=decision.reason,
                decision=decision,
            )
            self._audit(request, decision, result)
            return result
        result = runner(request)
        result.decision = decision
        self._audit(request, decision, result)
        return result

    def call_approved(self, request: ToolCallRequest, human_approved: bool) -> ToolCallResult:
        """带人工批准凭证的执行路径（AGENT-LOOP-03）。

        human_approved=True 且风险 <= R3 时放行人工门；R4（网络/发布）不在本方法
        放行。路径 allowlist 与审计照常生效。这使审批显式且可审计，而非旁路策略。
        """
        from udify.core.tool_gateway.policy import RiskLevel

        decision = self.policy.evaluate(
            tool_id=request.tool_id,
            capability=request.capability,
            requested_paths=request.requested_paths or None,
            timeout=request.timeout,
        )
        if decision.requires_human_confirmation and not human_approved:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason="requires human confirmation",
                decision=decision,
            )
            self._audit(request, decision, result)
            return result
        if decision.risk >= RiskLevel.R4:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason="R4 requires elevated approval, not approvable here",
                decision=decision,
            )
            self._audit(request, decision, result)
            return result
        # 已批准且 <= R3：直接执行（不再次走 policy.block），审计一致。
        timeout = (
            request.timeout if request.timeout is not None else self.policy.max_timeout_seconds
        )
        import time

        start = time.monotonic()
        try:
            proc = subprocess.run(request.args, capture_output=True, text=True, timeout=timeout)
            duration = time.monotonic() - start
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            artifact = None
            if len(stdout) > _MAX_INLINE_OUTPUT and self.artifact_dir is not None:
                artifact = self._write_artifact(request, stdout)
                stdout = stdout[:_MAX_INLINE_OUTPUT] + "\n[truncated, see artifact]"
            result = ToolCallResult(
                success=proc.returncode == 0,
                return_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                output_artifact=artifact,
                decision=decision,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            result = ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"timed out after {timeout}s",
                blocked_reason="timeout",
                decision=decision,
            )
        except FileNotFoundError:
            result = ToolCallResult(
                success=False,
                return_code=None,
                stderr=f"tool not found: {request.args[0] if request.args else ''}",
                blocked_reason="tool_not_found",
                decision=decision,
            )
        self._audit(request, decision, result)
        return result

    def call_sandboxed(
        self,
        request: ToolCallRequest,
        sandbox_executor: Any,
        human_approved: bool = False,
    ) -> ToolCallResult:
        """R3+ 工具调用经沙箱执行（iter3 N3 / S4-SANDBOX）。

        fail-closed：R3+ 操作必须经沙箱；沙箱不可用（backend 返回
        seatbelt_unavailable 等）则拒绝，不降级为普通 subprocess。R4 仍需更高级别
        流程。审计照常覆盖。这修复 iter2 call_approved 直接 subprocess 绕沙箱的缺口。
        """
        from udify.core.tool_gateway.policy import RiskLevel

        decision = self.policy.evaluate(
            tool_id=request.tool_id,
            capability=request.capability,
            requested_paths=request.requested_paths or None,
            timeout=request.timeout,
        )
        # R3+ 需人工门
        if decision.requires_human_confirmation and not human_approved:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason="requires human confirmation",
                decision=decision,
            )
            self._audit(request, decision, result)
            return result
        # R4 不在本路径放行
        if decision.risk >= RiskLevel.R4:
            result = ToolCallResult(
                success=False,
                return_code=None,
                blocked_reason="R4 requires elevated approval",
                decision=decision,
            )
            self._audit(request, decision, result)
            return result
        # 经沙箱执行（runner = sandbox_executor.run）
        result = sandbox_executor.run(request)
        result.decision = decision
        # fail-closed：沙箱不可用则拒绝
        if result.blocked_reason in {"seatbelt_unavailable", "sandbox_unavailable"}:
            result.success = False
            result.blocked_reason = "sandbox unavailable (fail-closed, no degrade)"
        self._audit(request, decision, result)
        return result

    def _write_artifact(self, request: ToolCallRequest, content: str) -> str:
        assert self.artifact_dir is not None
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / f"{request.tool_id}_{request.job_id or 'out'}.txt"
        path.write_text(content)
        return str(path)

    def _audit(
        self, request: ToolCallRequest, decision: PolicyDecision, result: ToolCallResult
    ) -> None:
        record = ToolCallRecord(
            timestamp=now_iso(),
            tool_id=request.tool_id,
            capability=request.capability,
            args={"args": request.args},
            requested_paths=[str(p) for p in request.requested_paths],
            risk=decision.risk.name,
            decision="allowed" if decision.allowed else "blocked",
            success=result.success,
            return_code=result.return_code,
            duration_seconds=result.duration_seconds,
            output_artifact=result.output_artifact,
        )
        self.audit.append(record)


__all__ = ["ToolCallRequest", "ToolCallResult", "ToolGateway"]
