"""
Planning Engine - Action Space

ActionSpace 定义了给定状态下所有可能的合法动作。
它将用户意图转化为具体的 PatchOperation 候选。

设计原则：
1. 动作是领域无关的（统一使用 PatchOperation）
2. 动作生成是上下文感知的（考虑意图和约束）
3. 动作空间可以被剪枝（减少搜索空间）
"""

from __future__ import annotations

import random
from typing import Any

from udify.core.planning.state import Intent, PlanContext, PlanState
from udify.models.cdl_patch import (
    OpType,
    PatchOperation,
    create_add_edge_op,
    create_add_node_op,
    create_modify_property_op,
    create_remove_edge_op,
    create_remove_node_op,
)
from udify.models.content_graph import ContentGraph, ContentNode, EdgeType, NodeType


class ActionSpace:
    """
    动作空间生成器

    根据当前状态和意图，生成候选动作列表。
    """

    def __init__(
        self,
        max_candidates: int = 20,
        enable_add_node: bool = True,
        enable_remove_node: bool = True,
        enable_modify_property: bool = True,
        enable_add_edge: bool = True,
        enable_remove_edge: bool = True,
    ) -> None:
        self.max_candidates = max_candidates
        self.enable_add_node = enable_add_node
        self.enable_remove_node = enable_remove_node
        self.enable_modify_property = enable_modify_property
        self.enable_add_edge = enable_add_edge
        self.enable_remove_edge = enable_remove_edge

    def generate_actions(self, state: PlanState) -> list[PatchOperation]:
        """
        生成候选动作列表

        Args:
            state: 当前规划状态

        Returns:
            候选 PatchOperation 列表
        """
        actions: list[PatchOperation] = []
        graph = state.graph
        intent = state.intent
        context = state.context

        # 根据意图类型调整动作生成策略
        if "add" in intent.description.lower() or "create" in intent.description.lower():
            actions.extend(self._generate_add_actions(graph, intent, context))

        if "remove" in intent.description.lower() or "delete" in intent.description.lower():
            actions.extend(self._generate_remove_actions(graph, intent, context))

        if (
            "modify" in intent.description.lower()
            or "change" in intent.description.lower()
            or "update" in intent.description.lower()
        ):
            actions.extend(self._generate_modify_actions(graph, intent, context))

        # 如果意图不明确，生成混合动作
        if not actions:
            actions.extend(self._generate_add_actions(graph, intent, context))
            actions.extend(self._generate_modify_actions(graph, intent, context))
            actions.extend(self._generate_remove_actions(graph, intent, context))

        # 去重
        actions = self._deduplicate_actions(actions)

        # 剪枝到最大数量
        if len(actions) > self.max_candidates:
            # 优先保留与意图相关的动作
            scored_actions = [(a, self._score_action(a, intent)) for a in actions]
            scored_actions.sort(key=lambda x: x[1], reverse=True)
            actions = [a for a, _ in scored_actions[: self.max_candidates]]

        return actions

    def _generate_add_actions(
        self,
        graph: ContentGraph,
        intent: Intent,
        context: PlanContext,
    ) -> list[PatchOperation]:
        """生成添加类动作"""
        actions: list[PatchOperation] = []

        if not self.enable_add_node:
            return actions

        # 根据媒介类型和意图生成可能的节点类型
        node_types = self._suggest_node_types(graph, intent)

        for node_type in node_types[:5]:  # 限制每种类型的数量
            node_id = f"new_{node_type.name.lower()}_{random.randint(1000, 9999)}"
            actions.append(
                create_add_node_op(
                    node_id=node_id,
                    node_type=node_type,
                    name=f"New {node_type.name.title()}",
                    properties={"created_by_intent": intent.description[:50]},
                )
            )

        # 生成添加边的动作（连接新节点或现有节点）
        if self.enable_add_edge and len(graph.nodes) > 1:
            for _ in range(min(5, len(graph.nodes))):
                source = random.choice(graph.nodes)
                target = random.choice(graph.nodes)
                if source.id != target.id:
                    actions.append(
                        create_add_edge_op(
                            source=source.id,
                            target=target.id,
                            edge_type=EdgeType.DEPENDS_ON,
                        )
                    )

        return actions

    def _generate_remove_actions(
        self,
        graph: ContentGraph,
        intent: Intent,
        context: PlanContext,
    ) -> list[PatchOperation]:
        """生成删除类动作"""
        actions: list[PatchOperation] = []

        if not self.enable_remove_node:
            return actions

        # 根据保守性偏好限制删除数量
        max_removals = int((1.0 - context.preservative_bias) * 5)

        candidates = list(graph.nodes)
        if intent.priority_nodes:
            # 避免删除优先级节点
            candidates = [n for n in candidates if n.id not in intent.priority_nodes]

        for node in candidates[:max_removals]:
            # 避免删除根节点或核心机制
            if not self._is_critical_node(node):
                actions.append(create_remove_node_op(node.id))

        # 生成删除边的动作
        if self.enable_remove_edge and graph.edges:
            for edge in graph.edges[:max_removals]:
                actions.append(
                    create_remove_edge_op(
                        source=edge.source,
                        target=edge.target,
                        edge_type=edge.type,
                    )
                )

        return actions

    def _generate_modify_actions(
        self,
        graph: ContentGraph,
        intent: Intent,
        context: PlanContext,
    ) -> list[PatchOperation]:
        """生成修改类动作"""
        actions: list[PatchOperation] = []

        if not self.enable_modify_property:
            return actions

        # 根据意图确定要修改的属性
        target_properties = self._suggest_properties(intent)

        for node in graph.nodes[:10]:  # 限制候选节点数
            if intent.priority_nodes and node.id in intent.priority_nodes:
                # 优先修改优先级节点
                pass
            else:
                pass

            for prop_key, prop_value in target_properties.items():
                # 生成属性修改
                if prop_key in node.properties or random.random() < 0.3:
                    actions.append(
                        create_modify_property_op(
                            node_id=node.id,
                            key=prop_key,
                            value=prop_value,
                        )
                    )

        return actions

    def _suggest_node_types(self, graph: ContentGraph, intent: Intent) -> list[NodeType]:
        """根据意图建议节点类型"""
        # 默认类型
        defaults = [
            NodeType.MECHANIC,
            NodeType.ITEM,
            NodeType.CHARACTER,
            NodeType.EVENT,
        ]

        # 根据意图关键词调整
        desc = intent.description.lower()
        if any(w in desc for w in ["character", "npc", "hero", "player"]):
            return [NodeType.CHARACTER, NodeType.DIALOGUE] + defaults
        elif any(w in desc for w in ["item", "weapon", "armor", "potion"]):
            return [NodeType.ITEM, NodeType.MECHANIC] + defaults
        elif any(w in desc for w in ["level", "map", "area", "dungeon"]):
            return [NodeType.LEVEL, NodeType.EVENT] + defaults
        elif any(w in desc for w in ["quest", "mission", "task"]):
            return [NodeType.QUEST, NodeType.EVENT] + defaults

        return defaults

    def _suggest_properties(self, intent: Intent) -> dict[str, Any]:
        """根据意图建议属性修改"""
        desc = intent.description.lower()

        if "difficulty" in desc or "harder" in desc or "easier" in desc:
            return {"difficulty": "hard", "challenge_rating": 1.5}

        if "reward" in desc or "loot" in desc or "drop" in desc:
            return {"drop_rate": 2.0, "gold_reward": 1.5, "exp_reward": 1.5}

        if "speed" in desc or "fast" in desc:
            return {"speed_multiplier": 1.5, "animation_speed": 1.2}

        if "health" in desc or "damage" in desc:
            return {"health_multiplier": 1.2, "damage_multiplier": 1.1}

        # 默认：生成一些通用属性修改
        return {
            "enabled": True,
            "priority": random.randint(1, 10),
            "tags": ["modified"],
        }

    def _is_critical_node(self, node: ContentNode) -> bool:
        """判断节点是否为关键节点（不应被删除）"""
        # 根节点或核心机制节点
        if node.type in (NodeType.MECHANIC, NodeType.LEVEL) and "core" in node.name.lower():
            return True
        return bool("player" in node.name.lower() and node.type == NodeType.CHARACTER)

    def _deduplicate_actions(self, actions: list[PatchOperation]) -> list[PatchOperation]:
        """去重动作"""
        seen: set = set()
        result: list[PatchOperation] = []

        for action in actions:
            # 使用 PatchOperation 的自定义哈希
            if hash(action) not in seen:
                seen.add(hash(action))
                result.append(action)

        return result

    def _score_action(self, action: PatchOperation, intent: Intent) -> float:
        """为动作打分（用于排序）"""
        score = 1.0

        # 与意图关键词匹配加分
        desc = intent.description.lower()
        payload_str = str(action.payload).lower()

        # 简单的关键词匹配
        intent_words = set(desc.split())
        payload_words = set(payload_str.split())
        overlap = len(intent_words & payload_words)
        score += overlap * 0.5

        # 修改操作通常比删除操作更安全
        if action.op_type == OpType.MODIFY_PROPERTY:
            score += 0.3
        elif action.op_type == OpType.ADD_NODE:
            score += 0.2
        elif action.op_type == OpType.REMOVE_NODE:
            score -= 0.1

        return score
