"""
语义提升器（Semantic Lifter）—— PER-LIFT-01..04。

对应 ITERATION-PLAN-2026-07.md 批次 2 与 MODULE-ATTACK-MAP-v3 §5 PER-LIFT。

把解析出的"原始节点"（INI section / Lua 函数等）提升为带语义标签、证据、
置信度的节点，让 planner 能基于"这是 boss 的 MaxLife"而非"这是个叫 Boss
的节点的某个属性"来规划。

- PER-LIFT-01: domain ontology（boss/item/skill/quest/map）
- PER-LIFT-02: rule-based tagging（基于名称/属性模式打标签）
- PER-LIFT-03: evidence builder（每个标签有来源 SourceSpan）
- PER-LIFT-04: confidence scoring（rule/schema/context 加权）
"""

from __future__ import annotations

from dataclasses import dataclass, field

from udify.models.content_graph import ContentGraph, ContentNode, NodeType
from udify.models.source import Confidence, Evidence, SourceSpan, ToolRunRef

# --- PER-LIFT-01: domain ontology -------------------------------------------

# 角色/物品/技能/地图的识别关键词（miu2d 域本体初版）
_DOMAIN_ONTOLOGY: dict[str, list[str]] = {
    "boss": ["boss", "boss_", "finalboss", "魔王", "首领", "boss1", "boss2"],
    "enemy": ["enemy", "monster", "mob", "怪物", "敌人", "小怪"],
    "player": ["hero", "player", "主角", "主角", "主人公", "lead"],
    "item": ["item", "potion", "sword", "weapon", "道具", "物品", "装备"],
    "skill": ["skill", "magic", "spell", "技能", "法术"],
    "quest": ["quest", "mission", "task", "任务"],
    "map": ["map", "level", "stage", "dungeon", "地图", "关卡"],
    "npc": ["npc", "merchant", "villager", "村民", "商人"],
}

# 数值属性 → 语义类别（用于识别"这是个可调数值"）
_NUMERIC_ATTRIBUTES: dict[str, str] = {
    "maxlife": "health",
    "life": "health",
    "hp": "health",
    "maxmana": "mana",
    "mana": "mana",
    "mp": "mana",
    "attack": "offense",
    "atk": "offense",
    "damage": "offense",
    "defense": "defense",
    "def": "defense",
    "speed": "speed",
    "criticalrate": "critical",
    "critrate": "critical",
    "droprate": "drop",
    "drop": "drop",
    "exp": "experience",
    "expreward": "experience",
    "gold": "currency",
    "price": "currency",
    "level": "level",
}


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


@dataclass
class TagResult:
    """单个节点的打标签结果。"""

    tags: list[str] = field(default_factory=list)
    numeric_kinds: dict[str, str] = field(default_factory=dict)  # 属性键→语义类别
    evidence: list[Evidence] = field(default_factory=list)


class SemanticLifter:
    """语义提升器（PER-LIFT-01..04）。"""

    def __init__(self) -> None:
        self.ontology = _DOMAIN_ONTOLOGY
        self.numeric_attrs = _NUMERIC_ATTRIBUTES

    def lift_graph(self, graph: ContentGraph) -> None:
        """就地提升图中所有节点：打标签 + 构造证据 + 置信度。"""
        extractor = ToolRunRef(tool_id="semantic_lifter", version="1.0")
        for node in graph.nodes:
            self.lift_node(node, extractor)

    def lift_node(self, node: ContentNode, extractor: ToolRunRef | None = None) -> TagResult:
        """提升单个节点，返回标签结果并就地更新 node.semantic_tags/confidence。"""
        if extractor is None:
            extractor = ToolRunRef(tool_id="semantic_lifter", version="1.0")

        result = self._tag_node(node)

        # 写回节点（PER-LIFT-02/03/04）
        node.semantic_tags = list(result.tags)
        # 置信度：rule_confidence 主导（PER-LIFT-04，无 runtime/LLM 时）
        score = self._score_confidence(result, node)
        node.confidence = Confidence(
            score=score,
            method="rule" if score > 0 else "unknown",
            evidence_refs=tuple(e.evidence_id for e in result.evidence),
        )
        return result

    def _tag_node(self, node: ContentNode) -> TagResult:
        """PER-LIFT-02: 基于名称/属性模式打标签。"""
        result = TagResult()
        name_norm = _norm(node.name)

        # 1. 实体类型标签（boss/enemy/player/item/skill/...）
        for canonical, keywords in self.ontology.items():
            matched = False
            for kw in keywords:
                kw_norm = _norm(kw)
                if kw_norm and kw_norm in name_norm:
                    result.tags.append(canonical)
                    result.evidence.append(
                        self._make_evidence(
                            node, canonical, f"name '{node.name}' matches keyword '{kw}'"
                        )
                    )
                    matched = True
                    break
            if matched:
                break  # 一个实体类型即可

        # 补 NodeType 推断（如果没有 name 匹配，用 NodeType 兜底）
        if not result.tags:
            nt_map = {
                NodeType.CHARACTER: "character",
                NodeType.ITEM: "item",
                NodeType.EVENT: "event",
                NodeType.LEVEL: "map",
            }
            base = nt_map.get(node.type)
            if base:
                result.tags.append(base)

        # 2. 数值属性语义类别（PER-LIFT-02 的 numeric 侧）
        for key, value in node.properties.items():
            kind = self.numeric_attrs.get(_norm(key))
            if kind is not None and isinstance(value, (int, float)):
                result.numeric_kinds[key] = kind
                result.evidence.append(
                    self._make_evidence(
                        node,
                        f"numeric:{kind}",
                        f"property '{key}'={value} recognized as {kind}",
                    )
                )

        # 若节点有数值属性且是角色/敌人 → 补 "tunable" 标签
        if result.numeric_kinds and any(
            t in ("boss", "enemy", "player", "character") for t in result.tags
        ):
            result.tags.append("tunable")

        return result

    def _score_confidence(self, result: TagResult, node: ContentNode) -> float:
        """PER-LIFT-04: 置信度评分。

        简化的加权（无 runtime/LLM 时）：
          rule_confidence 主导 + schema（NodeType 一致）小幅加权。
        """
        if not result.tags:
            return 0.0
        # rule: 有 name 匹配的证据 → 高；仅 NodeType 兜底 → 中
        name_evidence = [e for e in result.evidence if "matches keyword" in e.description]
        rule = 0.9 if name_evidence else 0.5
        # schema: NodeType 与推断一致 → +0.1
        schema = 0.1 if node.type != NodeType.RESOURCE else 0.0
        score = rule * 0.85 + schema
        return min(1.0, score)

    def _make_evidence(self, node: ContentNode, tag: str, description: str) -> Evidence:
        """PER-LIFT-03: 为每个标签构造证据（指向来源 SourceSpan）。"""
        import uuid

        span = getattr(node, "source_span", None)
        return Evidence(
            evidence_id=f"ev_{uuid.uuid4().hex[:8]}",
            description=f"[{tag}] {description}",
            span=span if isinstance(span, SourceSpan) else None,
            payload={"node_id": node.id, "node_name": node.name},
        )


__all__ = ["SemanticLifter", "TagResult"]
