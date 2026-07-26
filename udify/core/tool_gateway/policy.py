"""
Secure Tool Gateway —— 策略决策（TOOL-GW-02..04）。

对应 ITERATION-PLAN-2026-07.md §4.3。所有外部工具调用必须经此唯一入口。
本文件实现本地策略决策（先不上 OPA）：路径 allowlist、风险分级、配额、超时。

强约束（§7.2）：工具调用参数由程序构造，不直接用模型原文；高风险调用由
Policy 决策，不由 LLM 决定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path


class RiskLevel(IntEnum):
    """风险分级（§7.1 R0–R4）。"""

    R0 = 0  # 读 manifest、解析文本 —— 自动
    R1 = 1  # 改 VFS 配置 —— 自动，记录
    R2 = 2  # 写工作区文件 —— 需验证通过
    R3 = 3  # 执行外部工具/脚本 —— 沙箱 + 策略
    R4 = 4  # 运行时 Hook、网络、发布 —— 人工确认


# 每个工具能力的默认风险等级
_DEFAULT_CAPABILITY_RISK: dict[str, RiskLevel] = {
    "read_file": RiskLevel.R0,
    "parse": RiskLevel.R0,
    "write_config": RiskLevel.R1,
    "write_workspace": RiskLevel.R2,
    "run_external_tool": RiskLevel.R3,
    "run_script": RiskLevel.R3,
    "runtime_hook": RiskLevel.R4,
    "network": RiskLevel.R4,
    "publish": RiskLevel.R4,
}


@dataclass
class PolicyDecision:
    """策略决策结果。"""

    allowed: bool
    risk: RiskLevel
    reason: str = ""
    requires_human_confirmation: bool = False
    sandbox_required: bool = False
    network_allowed: bool = False


@dataclass
class ToolPolicy:
    """本地工具策略（TOOL-GW-02）。

    Attributes:
        allowed_roots: 允许工具访问的根目录（game_root + workspace_cache）。
            任何越权路径请求直接拒绝。
        max_timeout_seconds: 单次调用超时上限。
        require_sandbox_above: 风险高于此级必须沙箱。
        require_confirmation_above: 风险高于此级必须人工确认。
        network_allowed_tools: 显式允许联网的工具白名单（默认空=全断网）。
    """

    allowed_roots: list[Path] = field(default_factory=list)
    max_timeout_seconds: int = 300
    require_sandbox_above: RiskLevel = RiskLevel.R2
    require_confirmation_above: RiskLevel = RiskLevel.R3
    network_allowed_tools: set[str] = field(default_factory=set)

    def evaluate(
        self,
        tool_id: str,
        capability: str,
        requested_paths: list[Path] | None = None,
        timeout: int | None = None,
    ) -> PolicyDecision:
        """评估一次工具调用是否被允许。"""
        risk = self._risk_for(capability)

        # 1. 路径 allowlist：仅允许 allowed_roots 下的路径
        if requested_paths:
            for p in requested_paths:
                if not self._is_path_allowed(p):
                    return PolicyDecision(
                        allowed=False,
                        risk=risk,
                        reason=f"path outside allowed roots: {p}",
                    )

        # 2. 超时
        effective_timeout = timeout if timeout is not None else self.max_timeout_seconds
        if effective_timeout > self.max_timeout_seconds:
            return PolicyDecision(
                allowed=False,
                risk=risk,
                reason=f"timeout {effective_timeout}s exceeds max {self.max_timeout_seconds}s",
            )

        # 3. 风险门槛
        requires_human = risk >= self.require_confirmation_above
        sandbox_required = risk >= self.require_sandbox_above
        network_allowed = tool_id in self.network_allowed_tools and risk <= RiskLevel.R3

        # R4 默认不允许自动执行（需人工确认后才由 gateway 放行）
        allowed = not requires_human

        return PolicyDecision(
            allowed=allowed,
            risk=risk,
            requires_human_confirmation=requires_human,
            sandbox_required=sandbox_required,
            network_allowed=network_allowed,
            reason="ok" if allowed else "requires human confirmation",
        )

    def _risk_for(self, capability: str) -> RiskLevel:
        return _DEFAULT_CAPABILITY_RISK.get(capability, RiskLevel.R3)

    def _is_path_allowed(self, path: Path) -> bool:
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            return False
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                return True
            except ValueError:
                continue
        return False


__all__ = ["PolicyDecision", "RiskLevel", "ToolPolicy"]
