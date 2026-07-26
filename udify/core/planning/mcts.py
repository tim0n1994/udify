"""
Planning Engine - MCTS Tree Search

MCTS (Monte Carlo Tree Search) 是规划引擎的核心搜索算法。
它通过迭代地构建搜索树来找到最优动作序列。

与传统 MCTS 的区别：
1. 动作空间是结构化的（PatchOperation 而非棋盘位置）
2. 价值函数由 LLM 提供（而非游戏胜负）
3. 支持早期终止（找到满意解时停止）
4. 支持约束传播（某些动作被禁止）
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from udify.core.planning.action_space import ActionSpace
from udify.core.planning.state import PlanState
from udify.core.planning.value_function import ValueFunction
from udify.models.cdl_patch import PatchOperation


@dataclass
class MCTSConfig:
    """MCTS 配置参数"""

    # 迭代次数
    num_iterations: int = 100

    # UCT 探索常数（越大越鼓励探索）
    exploration_constant: float = 1.414

    # 最大搜索深度（超过此深度强制终止）
    max_depth: int = 10

    # 是否启用快速 rollout
    enable_rollout: bool = True

    # Rollout 次数（每次模拟的随机走子步数）
    rollout_steps: int = 5

    # 提前终止阈值（价值超过此值时停止搜索）
    early_termination_threshold: float = 0.9

    # 并行度（如果支持并行 rollout）
    parallel_workers: int = 1

    # 是否使用价值函数缓存
    use_value_cache: bool = True

    # 节点扩展阈值（访问次数超过此值才扩展）
    expand_threshold: int = 1


@dataclass
class MCTSNode:
    """
    MCTS 树节点

    每个节点代表一个规划状态，包含：
    - 状态（PlanState）
    - 父节点和动作（从父节点到此节点的动作）
    - 子节点
    - 访问次数和价值总和（用于 UCT 计算）
    """

    state: PlanState
    parent: MCTSNode | None = None
    action: PatchOperation | None = None  # 从父节点到此节点的动作
    children: list[MCTSNode] = field(default_factory=list)

    # 统计信息
    visit_count: int = 0
    value_sum: float = 0.0

    # 是否已扩展
    is_expanded: bool = False

    # 未尝试的动作（用于扩展）
    untried_actions: list[PatchOperation] = field(default_factory=list)

    def is_fully_expanded(self) -> bool:
        """检查是否已完全扩展（所有动作都已尝试）"""
        return self.is_expanded and len(self.untried_actions) == 0

    def best_child(self, exploration_constant: float) -> MCTSNode:
        """
        使用 UCT 公式选择最佳子节点

        UCT = Q/N + c * sqrt(2 * ln(parent_N) / N)

        其中：
        - Q/N 是平均价值（exploitation）
        - c * sqrt(...) 是探索奖励（exploration）
        """
        if not self.children:
            raise ValueError("No children to select from")

        best_score = -float("inf")
        best_child_node: MCTSNode | None = None

        for child in self.children:
            if child.visit_count == 0:
                # 未访问过的节点给予无穷大探索奖励
                score = float("inf")
            else:
                exploitation = child.value_sum / child.visit_count
                exploration = exploration_constant * math.sqrt(
                    2 * math.log(self.visit_count) / child.visit_count
                )
                score = exploitation + exploration

            if score > best_score:
                best_score = score
                best_child_node = child

        if best_child_node is None:
            raise ValueError("Could not select best child")

        return best_child_node

    def update(self, value: float) -> None:
        """反向传播更新统计信息"""
        self.visit_count += 1
        self.value_sum += value

    def get_path(self) -> list[PatchOperation]:
        """获取从根节点到当前节点的动作序列"""
        path: list[PatchOperation] = []
        node: MCTSNode | None = self

        while node is not None and node.parent is not None:
            if node.action is not None:
                path.append(node.action)
            node = node.parent

        return list(reversed(path))

    def __repr__(self) -> str:
        return (
            f"MCTSNode(v={self.visit_count}, q={self.value_sum:.2f}, children={len(self.children)})"
        )


class MCTSTree:
    """
    MCTS 搜索树

    执行 MCTS 搜索的核心逻辑：
    1. Selection: 从根节点选择到叶子节点
    2. Expansion: 扩展叶子节点
    3. Simulation: 从叶子节点快速 rollout
    4. Backpropagation: 反向传播结果
    """

    def __init__(
        self,
        config: MCTSConfig,
        action_space: ActionSpace,
        value_function: ValueFunction,
    ) -> None:
        self.config = config
        self.action_space = action_space
        self.value_function = value_function
        self.root: MCTSNode | None = None

    def search(self, initial_state: PlanState) -> MCTSNode:
        """
        执行 MCTS 搜索

        Args:
            initial_state: 初始规划状态

        Returns:
            最佳终止节点（包含最优动作序列）
        """
        self.root = MCTSNode(state=initial_state.copy())

        for _iteration in range(self.config.num_iterations):
            # 1. Selection
            node = self._select(self.root)

            # 2. Expansion
            if not node.is_fully_expanded() and not node.state.is_terminal():
                node = self._expand(node)

            # 3. Simulation
            value = self._simulate(node)

            # 4. Backpropagation
            self._backpropagate(node, value)

            # 提前终止检查
            if self.value_function.is_terminal_good(node.state):
                break

        # 返回访问次数最多的子节点（最稳健的选择）
        if not self.root.children:
            return self.root

        return max(self.root.children, key=lambda n: n.visit_count)

    def _select(self, node: MCTSNode) -> MCTSNode:
        """
        选择阶段：从当前节点选择到最有潜力的叶子节点

        策略：
        - 如果节点未完全扩展，返回该节点
        - 否则使用 UCT 选择最佳子节点
        """
        while node.is_fully_expanded() and not node.state.is_terminal():
            if not node.children:
                break
            node = node.best_child(self.config.exploration_constant)

        return node

    def _expand(self, node: MCTSNode) -> MCTSNode:
        """
        扩展阶段：为叶子节点生成子节点

        策略：
        - 如果节点未初始化动作列表，生成候选动作
        - 选择一个未尝试的动作创建子节点
        """
        if not node.is_expanded:
            # 初始化动作列表
            actions = self.action_space.generate_actions(node.state)
            node.untried_actions = actions
            node.is_expanded = True

        if not node.untried_actions:
            return node

        # 随机选择一个未尝试的动作
        action = random.choice(node.untried_actions)
        node.untried_actions.remove(action)

        # 创建新状态
        new_state = node.state.copy()
        new_state.apply_action(action)

        # 创建子节点
        child = MCTSNode(
            state=new_state,
            parent=node,
            action=action,
        )
        node.children.append(child)

        return child

    def _simulate(self, node: MCTSNode) -> float:
        """
        模拟阶段：从当前节点进行快速 rollout

        策略：
        - 如果启用了 rollout，执行随机走子
        - 否则直接使用价值函数评估当前状态
        """
        if not self.config.enable_rollout or node.state.is_terminal():
            return self.value_function.evaluate(node.state)

        # 快速 rollout：随机执行几个动作
        sim_state = node.state.copy()

        for _ in range(self.config.rollout_steps):
            if sim_state.is_terminal():
                break

            actions = self.action_space.generate_actions(sim_state)
            if not actions:
                break

            action = random.choice(actions)
            sim_state.apply_action(action)

        return self.value_function.evaluate(sim_state)

    def _backpropagate(self, node: MCTSNode, value: float) -> None:
        """
        反向传播阶段：将模拟结果更新到路径上的所有节点
        """
        current: MCTSNode | None = node

        while current is not None:
            current.update(value)
            current = current.parent

    def get_best_path(self) -> list[PatchOperation]:
        """获取最佳路径（从根到访问次数最多的叶子）"""
        if self.root is None:
            return []

        if not self.root.children:
            return []

        # 找到访问次数最多的路径
        best_node = max(self.root.children, key=lambda n: n.visit_count)

        # 递归向下找到最深的节点
        while best_node.children:
            best_node = max(best_node.children, key=lambda n: n.visit_count)

        return best_node.get_path()

    def get_tree_stats(self) -> dict[str, Any]:
        """获取树的统计信息"""
        if self.root is None:
            return {"nodes": 0, "max_depth": 0}

        def count_nodes(node: MCTSNode) -> int:
            count = 1
            for child in node.children:
                count += count_nodes(child)
            return count

        def max_depth(node: MCTSNode) -> int:
            if not node.children:
                return 0
            return 1 + max(max_depth(child) for child in node.children)

        return {
            "nodes": count_nodes(self.root),
            "max_depth": max_depth(self.root),
            "root_visits": self.root.visit_count,
            "root_value": self.root.value_sum / max(self.root.visit_count, 1),
        }
