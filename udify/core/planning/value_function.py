"""
Planning Engine - Value Function

价值函数评估一个规划状态的好坏。这是 MCTS 的"启发式函数"，
可以由 LLM、轻量级模型或规则启发式实现。

设计原则：
1. 价值函数是独立的模块，可以被替换
2. 支持缓存避免重复计算
3. 支持批量评估提高效率
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from udify.core.planning.state import PlanState


class ValueFunction(ABC):
    """
    价值函数抽象基类
    
    评估给定规划状态的价值，返回 [-1, 1] 范围内的分数。
    1.0 表示完美满足意图，-1.0 表示完全违背意图。
    """
    
    @abstractmethod
    def evaluate(self, state: PlanState) -> float:
        """
        评估单个状态
        
        Args:
            state: 规划状态
        
        Returns:
            [-1, 1] 范围内的价值分数
        """
        pass
    
    def evaluate_batch(self, states: List[PlanState]) -> List[float]:
        """
        批量评估（默认实现是逐个评估）
        
        Args:
            states: 状态列表
        
        Returns:
            价值分数列表
        """
        return [self.evaluate(s) for s in states]
    
    def is_terminal_good(self, state: PlanState) -> bool:
        """
        判断终止状态是否"足够好"
        
        用于提前终止搜索（如果已经找到满意解）。
        """
        value = self.evaluate(state)
        return value > 0.8


class HeuristicValueFunction(ValueFunction):
    """
    启发式价值函数
    
    使用规则启发式快速评估状态，不需要 LLM。
    适用于：
    1. 快速原型验证
    2. MCTS 的 rollout 阶段
    3. 作为 LLM 价值函数的 fallback
    
    评估维度：
    1. 结构完整性（图是否仍然连通、一致）
    2. 意图匹配度（修改是否符合用户描述）
    3. 操作合理性（操作数量是否适中、是否有冗余）
    4. 保守性（是否保留了原始内容的重要部分）
    """
    
    def __init__(
        self,
        structure_weight: float = 0.25,
        intent_weight: float = 0.35,
        operation_weight: float = 0.20,
        preservative_weight: float = 0.20,
    ) -> None:
        self.structure_weight = structure_weight
        self.intent_weight = intent_weight
        self.operation_weight = operation_weight
        self.preservative_weight = preservative_weight
    
    def evaluate(self, state: PlanState) -> float:
        """评估状态价值"""
        if state._cached_value is not None:
            return state._cached_value
        
        scores = {
            "structure": self._evaluate_structure(state),
            "intent": self._evaluate_intent(state),
            "operation": self._evaluate_operations(state),
            "preservative": self._evaluate_preservative(state),
        }
        
        value = (
            scores["structure"] * self.structure_weight +
            scores["intent"] * self.intent_weight +
            scores["operation"] * self.operation_weight +
            scores["preservative"] * self.preservative_weight
        )
        
        # 裁剪到 [-1, 1]
        value = max(-1.0, min(1.0, value))
        
        state._cached_value = value
        return value
    
    def _evaluate_structure(self, state: PlanState) -> float:
        """评估图结构完整性"""
        graph = state.graph
        
        # 检查孤立节点
        connected_nodes = set()
        for edge in graph.edges:
            connected_nodes.add(edge.source)
            connected_nodes.add(edge.target)
        
        total_nodes = len(graph.nodes)
        if total_nodes == 0:
            return 0.0
        
        isolated_ratio = (total_nodes - len(connected_nodes)) / total_nodes
        
        # 检查是否有循环依赖（简化检查：边数不应远大于节点数）
        edge_node_ratio = len(graph.edges) / max(total_nodes, 1)
        density_penalty = 0.0
        if edge_node_ratio > 3.0:
            density_penalty = min(0.3, (edge_node_ratio - 3.0) * 0.1)
        
        score = 1.0 - isolated_ratio - density_penalty
        return max(0.0, score)
    
    def _evaluate_intent(self, state: PlanState) -> float:
        """评估意图匹配度"""
        intent = state.intent
        graph = state.graph
        
        if not intent.description:
            return 0.5  # 无明确意图时给中等分
        
        # 简单的关键词匹配
        desc = intent.description.lower()
        score = 0.3  # 基础分
        
        # 检查是否有操作执行
        if state.action_history:
            score += 0.2
        
        # 检查意图关键词是否出现在图的属性中
        intent_words = set(desc.split())
        graph_text = " ".join([
            n.name for n in graph.nodes
        ] + [
            str(p) for n in graph.nodes for p in n.properties.values() if isinstance(p, str)
        ]).lower()
        
        graph_words = set(graph_text.split())
        overlap = len(intent_words & graph_words)
        score += min(0.3, overlap * 0.05)
        
        # 优先节点是否被修改
        if intent.priority_nodes:
            modified_priority = sum(
                1 for op in state.action_history
                if op.target_id in intent.priority_nodes
            )
            score += min(0.2, modified_priority * 0.1)
        
        return min(1.0, score)
    
    def _evaluate_operations(self, state: PlanState) -> float:
        """评估操作合理性"""
        history = state.action_history
        context = state.context
        
        if not history:
            return 0.5  # 未执行操作
        
        # 操作数量适中加分
        op_count = len(history)
        if op_count <= 3:
            count_score = 1.0
        elif op_count <= context.max_operations // 2:
            count_score = 0.8
        elif op_count <= context.max_operations:
            count_score = 0.5
        else:
            count_score = 0.2
        
        # 检查冗余操作
        seen_targets: Dict[str, int] = {}
        redundancy_penalty = 0.0
        for op in history:
            key = f"{op.op_type.name}_{op.target_id}"
            seen_targets[key] = seen_targets.get(key, 0) + 1
            if seen_targets[key] > 2:
                redundancy_penalty += 0.1
        
        score = count_score - min(0.5, redundancy_penalty)
        return max(0.0, score)
    
    def _evaluate_preservative(self, state: PlanState) -> float:
        """评估保守性（保留原始内容的程度）"""
        context = state.context
        history = state.action_history
        
        if not history:
            return 1.0  # 完全保留
        
        # 计算修改率
        remove_count = sum(1 for op in history if "REMOVE" in op.op_type.name)
        modify_count = sum(1 for op in history if "MODIFY" in op.op_type.name)
        add_count = sum(1 for op in history if "ADD" in op.op_type.name)
        
        total = len(history)
        if total == 0:
            return 1.0
        
        # 删除操作权重最高（破坏性最强）
        destruction_score = (remove_count * 1.0 + modify_count * 0.5 + add_count * 0.2) / total
        
        # 根据保守性偏好调整
        score = 1.0 - destruction_score * (1.0 - context.preservative_bias)
        return max(0.0, score)


class LLMValueFunction(ValueFunction):
    """
    LLM 价值函数

    使用 LLM 评估状态价值。这是规划引擎的"导演"，
    提供高质量的评估但成本较高。

    如果 LLM 不可用，自动降级到启发式评估。
    """

    def __init__(self, model_name: str = "gpt-4o-mini", provider: str = "openai") -> None:
        self.model_name = model_name
        self.provider = provider
        self._cache: Dict[str, float] = {}
        self._llm: Optional[Any] = None
        self._heuristic = HeuristicValueFunction()
        self._llm_available: Optional[bool] = None

    def _get_llm(self) -> Any:
        """懒加载 LLM 客户端"""
        if self._llm is None:
            try:
                from udify.core.llm_client import LLMClient
                self._llm = LLMClient(provider=self.provider, model=self.model_name)
            except Exception:
                self._llm_available = False
                raise
        return self._llm

    def _check_available(self) -> bool:
        """检查 LLM 是否可用"""
        if self._llm_available is not None:
            return self._llm_available
        try:
            llm = self._get_llm()
            self._llm_available = llm.is_available()
            return self._llm_available
        except Exception:
            self._llm_available = False
            return False

    def evaluate(self, state: PlanState) -> float:
        """使用 LLM 评估状态"""
        state_hash = state.get_hash()

        if state_hash in self._cache:
            return self._cache[state_hash]

        # 如果 LLM 不可用，降级到启发式
        if not self._check_available():
            value = self._heuristic.evaluate(state)
            self._cache[state_hash] = value
            return value

        try:
            prompt = self._construct_prompt(state)
            llm = self._get_llm()
            response = llm.complete(prompt, temperature=0.3, max_tokens=50)
            value = self._parse_response(response.content)

            # 混合 LLM 和启发式结果（提高稳定性）
            heuristic_value = self._heuristic.evaluate(state)
            blended = 0.7 * value + 0.3 * heuristic_value
            blended = max(-1.0, min(1.0, blended))

            self._cache[state_hash] = blended
            return blended

        except Exception:
            # LLM 调用失败，降级到启发式
            value = self._heuristic.evaluate(state)
            self._cache[state_hash] = value
            return value

    def _construct_prompt(self, state: PlanState) -> str:
        """构造评估 prompt"""
        # 提取意图关键词
        intent = state.intent.description

        # 提取已执行的操作摘要
        action_summary = []
        for op in state.action_history[-10:]:  # 最近 10 个操作
            action_summary.append(f"- {op.op_type.name}: {op.target_id}")

        # 提取图状态摘要
        node_types: Dict[str, int] = {}
        for node in state.graph.nodes:
            nt = node.type.name
            node_types[nt] = node_types.get(nt, 0) + 1

        return f"""你是一位游戏 Mod 设计专家。请评估当前状态对以下意图的满足程度。

用户意图: {intent}

图状态摘要:
- 总节点数: {len(state.graph.nodes)}
- 总边数: {len(state.graph.edges)}
- 节点类型分布: {node_types}

最近执行的操作:
{chr(10).join(action_summary) if action_summary else "无"}

请评估当前状态满足用户意图的程度，返回一个 -1.0 到 1.0 之间的数字:
- 1.0 = 完美满足
- 0.0 = 中性/无影响
- -1.0 = 完全错误/破坏

只返回数字，不要其他文字。"""

    def _parse_response(self, content: str) -> float:
        """解析 LLM 响应为数值"""
        import re

        # 尝试提取数字
        numbers = re.findall(r"-?\d+\.?\d*", content.strip())
        if numbers:
            try:
                value = float(numbers[0])
                return max(-1.0, min(1.0, value))
            except ValueError:
                pass

        # 回退：检查正面/负面词汇
        positive = ["good", "great", "excellent", "perfect", "satisfied", "满足", "好", "优秀"]
        negative = ["bad", "poor", "wrong", "terrible", "破坏", "差", "错误"]

        content_lower = content.lower()
        pos_count = sum(1 for p in positive if p in content_lower)
        neg_count = sum(1 for n in negative if n in content_lower)

        if pos_count > neg_count:
            return 0.5
        elif neg_count > pos_count:
            return -0.5
        return 0.0
