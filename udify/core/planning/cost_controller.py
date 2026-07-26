"""
Udify Planning - Cost Controller

成本控制器：控制 LLM 调用成本和计算资源。
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from udify.core.infrastructure.config_center import config
from udify.core.planning.planner import PlanResult
from udify.core.planning.state import PlanState


@dataclass
class CostRecord:
    """成本记录"""

    operation: str
    cost_usd: float
    tokens_input: int = 0
    tokens_output: int = 0
    model: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))


@dataclass
class CostReport:
    """成本报告"""

    budget: float
    spent: float
    remaining: float
    records: list[CostRecord]
    savings: float = 0.0
    llm_calls: int = 0
    local_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": self.budget,
            "spent": self.spent,
            "remaining": self.remaining,
            "savings": self.savings,
            "llm_calls": self.llm_calls,
            "local_calls": self.local_calls,
            "record_count": len(self.records),
        }


def _norm_key(s: str) -> str:
    """归一化属性键：小写并去掉非字母数字字符（``MaxLife``/``max_life`` → ``maxlife``）。"""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _find_key_ci(props: dict, target: str) -> str | None:
    """在属性字典中大小写/分隔符不敏感地查找目标键，返回原始键名。"""
    norm_target = _norm_key(target)
    for k in props:
        if _norm_key(k) == norm_target:
            return k
    return None


class LocalModelPlanner:
    """
    本地模型规划器（降级策略）

    当 LLM 不可用或成本超支时使用。
    基于规则启发式，质量较低但免费。
    """

    async def plan(self, state: PlanState) -> PlanResult:
        """使用本地启发式规划"""
        from udify.models.cdl_patch import (
            create_modify_property_op,
        )

        # 简单的规则匹配
        intent = state.intent.description.lower()
        actions = []

        # 数值类意图
        if any(w in intent for w in ["血量", "hp", "生命", "life"]):
            for node in state.graph.nodes[:3]:
                if "boss" in node.name.lower() or "enemy" in node.name.lower():
                    # 属性键大小写不敏感匹配（miu2d INI 用 MaxLife，其它来源可能用 max_life）
                    life_key = _find_key_ci(node.properties, "max_life")
                    cur_life = (
                        node.properties[life_key]
                        if life_key
                        else node.properties.get("max_life", 100)
                    )
                    actions.append(
                        create_modify_property_op(
                            node_id=node.id,
                            key=life_key or "max_life",
                            value=cur_life * 2,
                        )
                    )

        # 经验类意图
        if any(w in intent for w in ["经验", "exp", "升级", "level"]):
            for node in state.graph.nodes[:3]:
                exp_key = _find_key_ci(node.properties, "exp_reward")
                cur_exp = (
                    node.properties[exp_key] if exp_key else node.properties.get("exp_reward", 10)
                )
                actions.append(
                    create_modify_property_op(
                        node_id=node.id,
                        key=exp_key or "exp_reward",
                        value=cur_exp * 2,
                    )
                )

        from udify.core.planning.planner import PlanResult

        return PlanResult(
            actions=actions,
            estimated_value=0.5,  # 本地模型质量中等
            explanation=f"[Local Model] 基于规则匹配生成 {len(actions)} 个操作",
            success=len(actions) > 0,
        )


class CostController:
    """
    成本控制器

    特性:
    - 预算制（每会话上限）
    - LLM 成本追踪
    - 自动降级（LLM → 本地模型）
    - 成本预警
    """

    def __init__(self, budget: float | None = None) -> None:
        self.budget = budget or config.cost.budget_per_session
        self.spent = 0.0
        self.records: list[CostRecord] = []
        self.local_model = LocalModelPlanner()
        self._llm_client: Any | None = None

    def set_llm_client(self, client: Any) -> None:
        """设置 LLM 客户端"""
        self._llm_client = client

    async def plan_with_budget(
        self,
        state: PlanState,
        planning_func: Callable[[PlanState], Coroutine[Any, Any, PlanResult]],
    ) -> PlanResult:
        """在预算内规划"""

        # 1. 估算成本
        estimated_cost = self._estimate_cost(state)

        # 2. 检查预算
        if self.spent + estimated_cost > self.budget * 0.9:
            # 预算紧张，直接使用本地模型
            return await self._plan_with_local_model(state)

        if self.spent + estimated_cost > self.budget:
            # 超出预算，拒绝
            from udify.core.planning.planner import PlanResult

            return PlanResult(
                actions=[],
                estimated_value=0.0,
                explanation="成本超出预算，请简化意图或增加预算",
                success=False,
            )

        # 3. 尝试使用 LLM
        try:
            start_time = datetime.now().replace(tzinfo=None)
            result = await planning_func(state)
            end_time = datetime.now().replace(tzinfo=None)

            # 计算实际成本
            actual_cost = self._calculate_cost(
                tokens_input=len(str(state)),
                tokens_output=len(str(result)),
                duration=(end_time - start_time).total_seconds(),
            )

            self._record_cost("planning", actual_cost)

            # 检查是否超支
            if self.spent > self.budget:
                # 回滚这次成本记录，返回本地模型结果
                self.spent -= actual_cost
                self.records.pop()
                return await self._plan_with_local_model(state)

            return result

        except Exception:
            # LLM 失败，降级到本地模型
            self._record_cost("planning_failed", 0.0)
            return await self._plan_with_local_model(state)

    def _estimate_cost(self, state: PlanState) -> float:
        """估算规划成本"""
        # 基于意图复杂度和图谱大小
        complexity = len(state.intent.description) / 100
        graph_size = len(state.graph.nodes) / 1000
        base_cost = 0.01  # 基础成本
        return base_cost + complexity * graph_size * 0.05

    def _calculate_cost(self, tokens_input: int, tokens_output: int, duration: float) -> float:
        """计算实际成本"""
        # 简化的成本模型：$0.001 per 1K tokens
        total_tokens = tokens_input + tokens_output
        token_cost = (total_tokens / 1000) * 0.001
        time_cost = min(duration * 0.001, 0.01)  # 时间成本上限
        return token_cost + time_cost

    def _record_cost(self, operation: str, cost: float, **kwargs) -> None:
        """记录成本"""
        self.spent += cost
        self.records.append(
            CostRecord(
                operation=operation,
                cost_usd=cost,
                **kwargs,
            )
        )

    async def _plan_with_local_model(self, state: PlanState) -> PlanResult:
        """使用本地模型规划"""
        result = await self.local_model.plan(state)
        self._record_cost("local_planning", 0.0, model="local")
        return result

    def get_report(self) -> CostReport:
        """生成成本报告"""
        llm_calls = sum(1 for r in self.records if r.operation == "planning")
        local_calls = sum(1 for r in self.records if r.operation == "local_planning")

        return CostReport(
            budget=self.budget,
            spent=self.spent,
            remaining=self.budget - self.spent,
            records=self.records,
            savings=self.budget - self.spent,
            llm_calls=llm_calls,
            local_calls=local_calls,
        )

    def check_budget(self) -> dict[str, Any]:
        """检查预算状态"""
        remaining = self.budget - self.spent
        ratio = self.spent / self.budget if self.budget > 0 else 0

        status = "healthy"
        if ratio > 0.9:
            status = "critical"
        elif ratio > 0.7:
            status = "warning"
        elif ratio > 0.5:
            status = "caution"

        return {
            "budget": self.budget,
            "spent": self.spent,
            "remaining": remaining,
            "ratio": ratio,
            "status": status,
            "llm_calls": sum(1 for r in self.records if r.operation == "planning"),
            "local_calls": sum(1 for r in self.records if r.operation == "local_planning"),
        }
