"""
Planning Engine - State Representation

PlanState 是规划过程中的状态表示，包含：
- 当前内容图谱（ContentGraph）
- 用户意图（Intent）
- 上下文信息（约束、偏好、历史）
- 已执行的动作序列
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from udify.models.content_graph import ContentGraph
from udify.models.cdl_patch import CDLPatch, PatchOperation


@dataclass
class Intent:
    """
    用户意图
    
    将自然语言描述转化为结构化的规划约束。
    """
    description: str = ""  # 原始自然语言描述
    target_media_type: Optional[str] = None  # 目标媒介类型
    priority_nodes: List[str] = field(default_factory=list)  # 重点关注的节点 ID
    constraints: List[str] = field(default_factory=list)  # 约束条件（如"不要修改战斗系统"）
    style_hints: Dict[str, Any] = field(default_factory=dict)  # 风格提示
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "target_media_type": self.target_media_type,
            "priority_nodes": self.priority_nodes,
            "constraints": self.constraints,
            "style_hints": self.style_hints,
        }


@dataclass
class PlanContext:
    """
    规划上下文
    
    包含影响规划决策的额外信息。
    """
    # 技术约束
    max_operations: int = 50  # 最大操作数
    max_depth: int = 10  # 最大搜索深度
    forbidden_patterns: List[str] = field(default_factory=list)  # 禁止的模式
    
    # 用户偏好
    risk_tolerance: float = 0.5  # 风险容忍度 (0.0-1.0)
    preservative_bias: float = 0.7  # 保留原始内容的偏好 (0.0-1.0)
    
    # 历史信息
    previous_patches: List[CDLPatch] = field(default_factory=list)  # 已应用的 patches
    successful_patterns: List[str] = field(default_factory=list)  # 历史上成功的模式
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_operations": self.max_operations,
            "max_depth": self.max_depth,
            "forbidden_patterns": self.forbidden_patterns,
            "risk_tolerance": self.risk_tolerance,
            "preservative_bias": self.preservative_bias,
            "previous_patches_count": len(self.previous_patches),
        }


@dataclass
class PlanState:
    """
    规划状态
    
    表示规划过程中的一个具体状态，可以被 MCTS 节点引用。
    为了支持 MCTS 的 rollout，需要支持高效的拷贝和修改。
    """
    graph: ContentGraph
    intent: Intent
    context: PlanContext
    
    # 已执行的操作序列（从根到当前）
    action_history: List[PatchOperation] = field(default_factory=list)
    
    # 当前深度
    depth: int = 0
    
    # 缓存的评估值（避免重复计算）
    _cached_value: Optional[float] = field(default=None, repr=False)
    
    def copy(self) -> PlanState:
        """创建状态的深拷贝（用于 MCTS rollout）"""
        return PlanState(
            graph=deepcopy(self.graph),
            intent=self.intent,  # Intent 是只读的，不需要深拷贝
            context=self.context,  # Context 是只读的
            action_history=list(self.action_history),  # 浅拷贝即可（PatchOperation 是不可变的）
            depth=self.depth,
        )
    
    def apply_action(self, action: PatchOperation) -> PlanState:
        """
        应用动作并返回新状态
        
        注意：这会修改当前状态的图！如果需要在多个分支中复用，
        请先调用 copy()。
        """
        from udify.models.cdl_patch import PatchApplicator
        
        applicator = PatchApplicator()
        patch = CDLPatch(operations=[action], intent=f"Rollout action: {action.op_type.name}")
        
        success, _ = applicator.apply(patch, self.graph, validate=True, atomic=True)
        
        if success:
            self.action_history.append(action)
            self.depth += 1
            self._cached_value = None  # 重置缓存
        
        return self
    
    def is_terminal(self) -> bool:
        """
        检查是否为终止状态
        
        终止条件：
        1. 达到最大深度
        2. 意图已满足（由价值函数判断）
        3. 无法执行更多有效操作
        """
        return self.depth >= self.context.max_depth
    
    def get_hash(self) -> str:
        """生成状态的紧凑哈希（用于 MCTS 树中的重复检测）"""
        # 使用图的摘要信息 + 深度 + 操作历史长度
        graph_hash = f"{len(self.graph.nodes)}_{len(self.graph.edges)}_{len(self.graph.assets)}"
        action_hash = f"{self.depth}_{len(self.action_history)}"
        return f"{graph_hash}_{action_hash}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_summary": self.graph.summary(),
            "intent": self.intent.to_dict(),
            "context": self.context.to_dict(),
            "depth": self.depth,
            "action_count": len(self.action_history),
        }
