"""
Udify Core - Planning Engine

规划引擎：基于 MCTS + LLM 价值函数的意图驱动规划器。

设计哲学：
- LLM 是"导演"，负责评估状态价值和生成创意
- MCTS 是"制片人"，负责系统性搜索和决策优化
- 专用工具是"演员"，负责执行具体操作

核心流程：
1. Selection: 选择最有潜力的节点（UCT 公式）
2. Expansion: 展开新节点（ActionSpace 生成候选动作）
3. Simulation: 快速 rollout（轻量级启发式或 LLM 评估）
4. Backpropagation: 更新路径上的统计信息
"""

from udify.core.planning.action_space import ActionSpace
from udify.core.planning.mcts import MCTSConfig, MCTSNode, MCTSTree
from udify.core.planning.planner import Planner, PlanResult
from udify.core.planning.state import PlanState
from udify.core.planning.value_function import HeuristicValueFunction, ValueFunction

__all__ = [
    "ActionSpace",
    "MCTSConfig",
    "MCTSNode",
    "MCTSTree",
    "Planner",
    "PlanResult",
    "PlanState",
    "HeuristicValueFunction",
    "ValueFunction",
]
