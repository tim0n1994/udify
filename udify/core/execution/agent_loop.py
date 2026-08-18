"""
安全 Agent 循环骨架（AGENT-LOOP-01..04，第二轮大迭代）。

把 Planner 决策 -> ToolGateway -> 审计 -> 人工门 串成一个显式状态机。
设计原则（来自 R5-AGENT 深度研究）：
- LangGraph 风格的显式状态图，但本轮用 stdlib 实现，不锁 LangGraph 版本。
- 工具调用必须经 ToolGateway（注入），禁止旁路。
- R3+（>= require_confirmation_above）操作进入 AWAITING_HUMAN，未批准不执行。
- 审计链覆盖每次工具调用，可验证完整性。

LLM 不内置：plan 阶段是一个可注入的 callable，这样无 key 也能测。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from udify.core.tool_gateway.audit import ToolAuditChain
from udify.core.tool_gateway.gateway import ToolCallRequest, ToolCallResult, ToolGateway


class AgentState(Enum):
    """Agent 循环状态。"""

    PLANNING = auto()
    AWAITING_TOOL = auto()
    AWAITING_HUMAN = auto()
    EXECUTING = auto()
    AUDITING = auto()
    DONE = auto()
    FAILED = auto()


@dataclass
class AgentAction:
    """规划器产出的一个候选动作（候选身份，需经 gateway 策略裁决）。"""

    tool_id: str
    capability: str
    args: list[str] = field(default_factory=list)
    requested_paths: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class AgentResult:
    """一次循环的最终结果。"""

    state: AgentState
    results: list[ToolCallResult] = field(default_factory=list)
    blocked: list[AgentAction] = field(default_factory=list)
    error: str | None = None


class AgentLoop:
    """安全 Agent 循环。

    Args:
        gateway: 工具网关（唯一工具入口，禁止旁路）。
        audit: 审计链。
        planner: 规划 callable，输入上下文，返回候选 AgentAction 列表。
            LLM 是可选增强；无 key 时 planner 可以是规则/启发式。
    """

    def __init__(
        self,
        gateway: ToolGateway,
        audit: ToolAuditChain,
        planner: Callable[[dict[str, Any]], list[AgentAction]],
    ) -> None:
        self.gateway = gateway
        self.audit = audit
        self.planner = planner
        self._state: AgentState = AgentState.PLANNING

    @property
    def state(self) -> AgentState:
        return self._state

    def run(
        self,
        context: dict[str, Any],
        approved_human: bool = False,
    ) -> AgentResult:
        """执行一轮 plan -> (gate) -> execute -> audit。

        Args:
            context: 传给 planner 的上下文。
            approved_human: 是否已获得人工批准（用于 R3+ 放行）。

        Returns:
            AgentResult，含每次工具结果与被拦动作。
        """
        result = AgentResult(state=AgentState.PLANNING)
        try:
            actions = self.planner(context) or []
        except Exception as exc:  # planner 失败即循环失败
            self._state = AgentState.FAILED
            result.state = AgentState.FAILED
            result.error = f"planner failed: {exc}"
            return result

        for action in actions:
            self._state = AgentState.AWAITING_TOOL
            request = ToolCallRequest(
                tool_id=action.tool_id,
                capability=action.capability,
                args=list(action.args),
                requested_paths=[_to_path(p) for p in action.requested_paths],
            )
            # 先做策略预检：R3+ 需人工门
            decision = self.gateway.policy.evaluate(
                tool_id=action.tool_id,
                capability=action.capability,
                requested_paths=request.requested_paths or None,
            )
            if decision.requires_human_confirmation and not approved_human:
                self._state = AgentState.AWAITING_HUMAN
                result.blocked.append(action)
                continue

            self._state = AgentState.EXECUTING
            # R3+ 已批准时走显式审批路径（仍审计、仍 allowlist）；否则走标准 call
            if decision.requires_human_confirmation and approved_human:
                tool_result = self.gateway.call_approved(request, human_approved=True)
            else:
                tool_result = self.gateway.call(request)
            result.results.append(tool_result)
            self._state = AgentState.AUDITING

        # 完整性校验：所有记录链式哈希未被篡改
        if not self.audit.verify():
            self._state = AgentState.FAILED
            result.state = AgentState.FAILED
            result.error = "audit chain integrity broken"
            return result

        self._state = AgentState.DONE if not result.blocked else AgentState.AWAITING_HUMAN
        result.state = self._state
        return result


def _to_path(p: str):
    from pathlib import Path

    return Path(p)


__all__ = ["AgentAction", "AgentLoop", "AgentResult", "AgentState"]
