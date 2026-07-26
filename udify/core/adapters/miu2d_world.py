"""
miu2d GameWorldGraph 构建器（ADAPT-MIU2D-06）。

MODULE-ATTACK-MAP-v3 §5 ADAPT-MIU2D-06：『GameWorldGraph builder ｜ config +
script ｜ 角色、物品、技能、地图关系』。

把感知产出的扁平节点图提升为"游戏世界图"——建立角色↔物品（拥有）、
角色↔技能（掌握）、NPC↔对话、地图↔事件等关系边，让 planner 知道"改这个
boss 的 HP 会影响哪些关联实体"。

这是 ADAPT-MIU2D 适配器感知能力的最终聚合层。
"""

from __future__ import annotations

from pathlib import Path

from udify.core.adapters.miu2d import Miu2dAdapter
from udify.core.perception.semantic_lifter import SemanticLifter
from udify.models.content_graph import ContentEdge, ContentGraph, EdgeType


class GameWorldGraphBuilder:
    """miu2d 游戏世界图构建器（ADAPT-MIU2D-06）。"""

    def __init__(self, adapter: Miu2dAdapter | None = None) -> None:
        self.adapter = adapter or Miu2dAdapter()
        self.lifter = SemanticLifter()

    def build(self, game_root: Path) -> ContentGraph:
        """构建游戏世界图：感知 → 语义提升 → 关系推断。"""
        # 1. 基础感知（带 SourceSpan）
        graph = self.adapter.perceive(game_root)

        # 2. 语义提升（PER-LIFT：打标签 + 证据 + 置信度）
        self.lifter.lift_graph(graph)

        # 3. 关系推断（建立实体间边）
        self._infer_relations(graph)

        return graph

    def _infer_relations(self, graph: ContentGraph) -> None:
        """推断实体间关系，写入边。"""
        nodes_by_tag = self._group_by_tags(graph)

        # 角色拥有物品：角色名出现在物品名/属性中（启发式）
        characters = (
            nodes_by_tag.get("character", [])
            + nodes_by_tag.get("player", [])
            + nodes_by_tag.get("boss", [])
            + nodes_by_tag.get("enemy", [])
        )
        items = nodes_by_tag.get("item", [])
        skills = nodes_by_tag.get("skill", [])

        # 同文件中的角色与物品建立 REFERENCES 关系
        for char in characters:
            for item in items:
                if self._same_source(char, item):
                    graph.add_edge(
                        ContentEdge(
                            source=char.id,
                            target=item.id,
                            type=EdgeType.REFERENCES,
                            properties={"inferred": True, "reason": "same_source_file"},
                        )
                    )

        # 角色掌握技能
        for char in characters:
            for skill in skills:
                if self._same_source(char, skill):
                    graph.add_edge(
                        ContentEdge(
                            source=char.id,
                            target=skill.id,
                            type=EdgeType.REQUIRES,
                            properties={"inferred": True, "reason": "skill_association"},
                        )
                    )

        # 脚本节点（lua_function）与同文件的危险调用建立 TRIGGERS 关系
        dangerous = [n for n in graph.nodes if "dangerous_api" in n.semantic_tags]
        functions = [n for n in graph.nodes if "lua_function" in n.semantic_tags]
        for func in functions:
            for danger in dangerous:
                if self._same_source(func, danger):
                    graph.add_edge(
                        ContentEdge(
                            source=func.id,
                            target=danger.id,
                            type=EdgeType.TRIGGERS,
                            properties={"inferred": True, "reason": "contains_dangerous_call"},
                        )
                    )

    def _group_by_tags(self, graph: ContentGraph) -> dict[str, list]:
        groups: dict[str, list] = {}
        for node in graph.nodes:
            for tag in node.semantic_tags:
                groups.setdefault(tag, []).append(node)
        return groups

    def _same_source(self, a, b) -> bool:
        sa = getattr(a, "source_path", None) or (
            getattr(a, "source_span", None) and a.source_span.file_path
        )
        sb = getattr(b, "source_path", None) or (
            getattr(b, "source_span", None) and b.source_span.file_path
        )
        return bool(sa and sb and sa == sb)


__all__ = ["GameWorldGraphBuilder"]
