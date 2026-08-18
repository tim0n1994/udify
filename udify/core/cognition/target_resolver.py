"""
目标节点解析（COG-LLM-01 / Reference Resolution，第二轮大迭代）。

解决真实缺陷："把 Boss 的血量翻倍"误伤 Hero。关键词引擎不做目标过滤，
本模块基于 ContentGraph 的语义字段（SEM-FIELD-01）做候选生成 + 硬约束
过滤 + 置信度排序，把"第一个 Boss"精确解析到目标节点。

LLM 是可选增强（候选身份）：无 key 时纯规则降级。最终目标节点由本模块
确定性裁决，LLM 不创造节点 ID、不输出路径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from udify.models.semantic import SemanticView, get_semantic

if TYPE_CHECKING:
    from udify.models.content_graph import ContentGraph, ContentNode


@dataclass
class TargetCandidate:
    """一个目标节点候选。"""

    node_id: str
    display_name: str | None
    semantic: SemanticView
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class TargetResolution:
    """目标解析结果。"""

    candidates: list[TargetCandidate] = field(default_factory=list)
    chosen: TargetCandidate | None = None
    ambiguous: bool = False

    def chosen_ids(self) -> list[str]:
        return [self.chosen.node_id] if self.chosen else []


# 目标描述关键词 -> 语义过滤谓词
_BOSS_KEYS = {"boss", "首领", "王", "头目", "领主", "最终boss", "最终 Boss"}
_PLAYER_KEYS = {"hero", "主角", "玩家", "勇者", "player", "主人公"}
_ENEMY_KEYS = {"enemy", "敌人", "怪物", "monster", "敌", "怪"}


def _matches_any(text: str, keys: set[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keys)


def resolve_targets(
    graph: ContentGraph,
    description: str,
    exclude_players: bool = True,
) -> TargetResolution:
    """把目标描述解析到 ContentGraph 中的节点。

    流程（确定性，无 LLM）：
    1. 候选生成：根据描述命中 Boss/敌人/玩家关键词筛选节点。
    2. 硬约束过滤：exclude_players=True 时排除 is_player 节点（防误伤 Hero）。
    3. 置信度排序：is_boss/高 hp 优先。
    4. 消歧：多个候选则 ambiguous=True，交审阅台/LLM 候选选择。

    Args:
        graph: 内容图谱。
        description: 目标描述（如"第一个 Boss""所有敌人"）。
        exclude_players: 是否排除玩家节点（默认 True，防误伤 Hero）。

    Returns:
        TargetResolution。
    """
    nodes: list[ContentNode] = list(getattr(graph, "nodes", []))
    want_boss = _matches_any(description, _BOSS_KEYS)
    want_enemy = _matches_any(description, _ENEMY_KEYS)
    want_player = _matches_any(description, _PLAYER_KEYS)

    candidates: list[TargetCandidate] = []
    for node in nodes:
        sem = get_semantic(node)
        # 硬约束：排除玩家（除非显式要玩家）
        if exclude_players and sem.is_player and not want_player:
            continue
        reasons: list[str] = []
        score = 0.0
        if want_boss and sem.is_boss:
            score += 1.0
            reasons.append("is_boss=True")
        if want_enemy and (sem.is_enemy or sem.is_boss):
            score += 0.5
            reasons.append("is_enemy/is_boss")
        if want_player and sem.is_player:
            score += 1.0
            reasons.append("is_player=True")
        # 战斗力倾向：高 hp 的更可能是"强敌"
        if sem.hp is not None and sem.hp > 0:
            score += min(sem.hp / 10000.0, 0.5)
            reasons.append(f"hp={sem.hp}")
        if score <= 0:
            continue
        candidates.append(
            TargetCandidate(
                node_id=node.id,
                display_name=sem.display_name or getattr(node, "name", None),
                semantic=sem,
                score=score,
                reasons=reasons,
            )
        )

    candidates.sort(key=lambda c: c.score, reverse=True)
    resolution = TargetResolution(candidates=candidates)
    if not candidates:
        return resolution
    # 单一明显胜出则选定；否则歧义
    if len(candidates) == 1 or (len(candidates) >= 2 and candidates[0].score > candidates[1].score):
        resolution.chosen = candidates[0]
    else:
        resolution.ambiguous = True
        resolution.chosen = candidates[0]  # 给最高分候选，但标记歧义
    return resolution


__all__ = ["TargetCandidate", "TargetResolution", "resolve_targets"]


def resolve_targets_grounded(
    graph: ContentGraph,
    description: str,
    exclude_players: bool = True,
) -> TargetResolution:
    """Grounded target resolution (iter5 U1-INTENT-GROUNDING PR2).

    Wraps resolve_targets with the ReferenceSpec disambiguation layer. When the
    description contains an ordinal ("first boss") or superlative ("strongest"),
    the ReferenceSpec resolver picks a unique node instead of leaving the result
    ambiguous. On disambiguation failure it marks the resolution ambiguous so
    the caller (pipeline/UI) can ask the user for clarification rather than
    silently guessing wrong — the exact bug that hit Hero instead of "first Boss".

    Falls back to plain resolve_targets for descriptions without ordinal/
    superlative patterns (backward compatible).
    """
    import re

    from udify.core.cognition.reference_spec import (
        OrderDomain,
        ReferenceOperator,
        ReferenceSpec,
    )
    from udify.core.cognition.reference_spec_resolver import (
        Success,
        resolve_reference,
    )

    # Detect ordinal/superlative intent; if none, use the existing resolver.
    ordinal_match = re.search(
        r"第\s*([一二三四五六七八九十\d]+)\s*个|first|第1|1st", description, re.IGNORECASE
    )
    superlative_match = re.search(
        r"最强|最高|weakest|strongest|max|min", description, re.IGNORECASE
    )
    if not ordinal_match and not superlative_match:
        return resolve_targets(graph, description, exclude_players)

    # Build a ReferenceSpec and run the grounded resolver.
    want_boss = _matches_any(description, _BOSS_KEYS)
    if not want_boss:
        return resolve_targets(graph, description, exclude_players)

    operator = ReferenceOperator.ORDINAL if ordinal_match else ReferenceOperator.SUPERLATIVE
    spec = ReferenceSpec(
        operator=operator,
        semantic_filters=(("is_boss", True),),
        ordinal=1 if ordinal_match else None,
        metric="attack" if superlative_match else None,
        maximize=True if superlative_match else None,
        order_domain=OrderDomain.DB_INDEX if ordinal_match else None,
    )
    result = resolve_reference(graph, spec)
    if isinstance(result, Success):
        # ResolvedReference carries node_id/name; find the actual node in the graph.
        resolved = result.reference
        node = next((n for n in graph.nodes if n.id == resolved.node_id), None)
        if node is None:
            base = resolve_targets(graph, description, exclude_players)
            base.ambiguous = True
            return base
        # Rebuild a single-candidate TargetResolution from the grounded node.
        from udify.models.semantic import get_semantic

        sem = get_semantic(node)
        chosen = TargetCandidate(
            node_id=node.id,
            display_name=node.name or None,
            semantic=sem,
            score=2.0,
            reasons=[f"grounded: {operator.value}", f"is_boss={sem.is_boss}"],
        )
        return TargetResolution(candidates=[chosen], chosen=chosen, ambiguous=False)
    # NeedsClarification or Failed: return ambiguous so the caller asks the user.
    base = resolve_targets(graph, description, exclude_players)
    base.ambiguous = True
    return base
