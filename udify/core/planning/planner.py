"""
Planning Engine - Main Planner

Planner 是规划引擎的入口，协调 ActionSpace、MCTS 和 ValueFunction
来完成从意图到动作序列的转换。

使用方式：
    planner = Planner()
    result = planner.plan(graph, intent="增加游戏难度")
    patch = result.to_patch()
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from udify.core.planning.action_space import ActionSpace
from udify.core.planning.mcts import MCTSConfig, MCTSTree
from udify.core.planning.state import Intent, PlanContext, PlanState
from udify.core.planning.value_function import HeuristicValueFunction, ValueFunction
from udify.models.cdl_patch import CDLPatch, PatchOperation
from udify.models.content_graph import ContentGraph


@dataclass
class PlanResult:
    """
    规划结果

    包含：
    - 最优动作序列
    - 预期价值
    - 搜索统计信息
    - 可解释性信息
    """

    actions: list[PatchOperation] = field(default_factory=list)
    estimated_value: float = 0.0
    search_stats: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    success: bool = False

    def to_patch(self, author: str = "planner") -> CDLPatch:
        """将规划结果转换为 CDLPatch"""
        return CDLPatch(
            operations=list(self.actions),
            intent=self.explanation,
            author=author,
        )

    def summary(self) -> str:
        """生成人类可读的结果摘要"""
        lines = [
            f"PlanResult: success={self.success}",
            f"  Estimated Value: {self.estimated_value:.3f}",
            f"  Actions: {len(self.actions)}",
            f"  Explanation: {self.explanation[:80]}{'...' if len(self.explanation) > 80 else ''}",
        ]

        if self.search_stats:
            lines.append(f"  Search Stats: {self.search_stats}")

        return "\n".join(lines)


class Planner:
    """
    规划器

    将用户意图转化为结构化的 CDLPatch。

    Attributes:
        config: MCTS 配置
        action_space: 动作空间生成器
        value_function: 价值函数（默认使用启发式）
    """

    def __init__(
        self,
        config: MCTSConfig | None = None,
        action_space: ActionSpace | None = None,
        value_function: ValueFunction | None = None,
    ) -> None:
        self.config = config or MCTSConfig()
        self.action_space = action_space or ActionSpace()
        self.value_function = value_function or HeuristicValueFunction()

    def plan(
        self,
        graph: ContentGraph,
        intent: str,
        context: PlanContext | None = None,
    ) -> PlanResult:
        """
        主规划入口

        Args:
            graph: 当前内容图谱
            intent: 用户意图描述（自然语言）
            context: 规划上下文（可选）

        Returns:
            PlanResult 包含最优动作序列
        """
        # 构建初始状态
        initial_state = PlanState(
            graph=graph,
            intent=Intent(description=intent),
            context=context or PlanContext(),
        )

        # 创建 MCTS 树
        tree = MCTSTree(
            config=self.config,
            action_space=self.action_space,
            value_function=self.value_function,
        )

        # 执行搜索
        best_node = tree.search(initial_state)

        # 提取结果
        actions = best_node.get_path()
        estimated_value = (
            best_node.value_sum / max(best_node.visit_count, 1)
            if best_node.visit_count > 0
            else 0.0
        )

        # 构建结果
        result = PlanResult(
            actions=actions,
            estimated_value=estimated_value,
            search_stats=tree.get_tree_stats(),
            explanation=self._generate_explanation(intent, actions, estimated_value),
            success=len(actions) > 0,
        )

        return result

    def plan_with_intent(
        self,
        graph: ContentGraph,
        intent: Intent,
        context: PlanContext | None = None,
    ) -> PlanResult:
        """
        使用结构化意图进行规划

        允许更精细的控制，如指定优先级节点和约束。
        """
        initial_state = PlanState(
            graph=graph,
            intent=intent,
            context=context or PlanContext(),
        )

        tree = MCTSTree(
            config=self.config,
            action_space=self.action_space,
            value_function=self.value_function,
        )

        best_node = tree.search(initial_state)
        actions = best_node.get_path()
        estimated_value = (
            best_node.value_sum / max(best_node.visit_count, 1)
            if best_node.visit_count > 0
            else 0.0
        )

        return PlanResult(
            actions=actions,
            estimated_value=estimated_value,
            search_stats=tree.get_tree_stats(),
            explanation=self._generate_explanation(intent.description, actions, estimated_value),
            success=len(actions) > 0,
        )

    def _generate_explanation(
        self,
        intent: str,
        actions: list[PatchOperation],
        value: float,
    ) -> str:
        """生成结果的可解释性描述"""
        if not actions:
            return f"No actions found for intent: '{intent}'. The graph may already satisfy the intent or no valid modifications were identified."

        op_summary: dict[str, int] = {}
        for op in actions:
            name = op.op_type.name
            op_summary[name] = op_summary.get(name, 0) + 1

        summary_parts = [f"{count} {name.lower()}" for name, count in op_summary.items()]

        return (
            f"To achieve '{intent}', planned {', '.join(summary_parts)}. "
            f"Estimated satisfaction: {value:.1%}."
        )
