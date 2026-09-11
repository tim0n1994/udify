"""
目标节点解析（COG-LLM-01 / Reference Resolution，第二轮大迭代）。

解决真实缺陷："把 Boss 的血量翻倍"误伤 Hero。关键词引擎不做目标过滤，
本模块基于 ContentGraph 的语义字段（SEM-FIELD-01）做候选生成 + 硬约束
过滤 + 有证据的序数/比较，把"第一个 Boss"精确解析到目标节点。

LLM 是可选增强（候选身份）：无 key 时纯规则降级。最终目标节点由本模块
确定性裁决，LLM 不创造节点 ID、不输出路径。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
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
    selected_ids: list[str] = field(default_factory=list)
    reason: str = ""

    def chosen_ids(self) -> list[str]:
        if self.ambiguous:
            return []
        return self.selected_ids or ([self.chosen.node_id] if self.chosen else [])


# 目标描述关键词 -> 语义过滤谓词
_BOSS_KEYS = {"boss", "首领", "王", "头目", "领主", "最终boss", "最终 Boss"}
_PLAYER_KEYS = {"hero", "主角", "玩家", "勇者", "player", "主人公"}
_ENEMY_KEYS = {"enemy", "敌人", "怪物", "monster", "敌", "怪"}
_ORDINAL_PATTERN = (
    r"第\s*([一二三四五六七八九十百\d]+)\s*个?|"
    r"\b(first|second|third|fourth|fifth|last)\b|"
    r"\b(\d+)(?:st|nd|rd|th)\b|最后(?:一)?个"
)


def _matches_any(text: str, keys: set[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keys)


def _semantic(node: ContentNode) -> SemanticView:
    sem = get_semantic(node)
    tags = set(node.semantic_tags)
    hp = node.properties.get("MaxLife", node.properties.get("maxhp"))
    return replace(
        sem,
        is_boss=sem.is_boss or "boss" in tags,
        is_player=sem.is_player or "player" in tags,
        is_enemy=sem.is_enemy or "enemy" in tags,
        hp=sem.hp
        if sem.hp is not None
        else (int(hp) if isinstance(hp, (int, float)) and not isinstance(hp, bool) else None),
    )


def _name_in_description(name: str, description: str) -> bool:
    if not name:
        return False
    return (
        re.search(
            r"(?<![a-z0-9_])" + re.escape(name.casefold()) + r"(?![a-z0-9_])",
            description.casefold(),
        )
        is not None
    )


def resolve_targets(
    graph: ContentGraph,
    description: str,
    exclude_players: bool = True,
) -> TargetResolution:
    """把目标描述解析到 ContentGraph 中的节点。

    流程（确定性，无 LLM）：
    1. 候选生成：根据描述命中 Boss/敌人/玩家关键词筛选节点。
    2. 硬约束过滤：exclude_players=True 时排除 is_player 节点（防误伤 Hero）。
    3. 明确复数时保留所有匹配目标；单数必须唯一。
    4. 多个单数候选返回 ambiguous=True，不以 HP 大小猜测用户选择。

    Args:
        graph: 内容图谱。
        description: 目标描述（如"第一个 Boss""所有敌人"）。
        exclude_players: 是否排除玩家节点（默认 True，防误伤 Hero）。

    Returns:
        TargetResolution。
    """
    nodes: list[ContentNode] = list(graph.nodes)
    want_boss = _matches_any(description, _BOSS_KEYS)
    want_enemy = _matches_any(description, _ENEMY_KEYS)
    want_player = _matches_any(description, _PLAYER_KEYS)

    role_words = _BOSS_KEYS | _PLAYER_KEYS | _ENEMY_KEYS
    named_nodes = [
        node
        for node in nodes
        if node.name.casefold() not in {word.casefold() for word in role_words}
        and _name_in_description(node.name, description)
    ]
    named_ids = {node.id for node in named_nodes}
    role_description = description
    for node in named_nodes:
        role_description = re.sub(re.escape(node.name), "", role_description, flags=re.I)
    requested_roles = [
        role
        for role, words in [
            ("is_boss", _BOSS_KEYS),
            ("is_player", _PLAYER_KEYS),
            ("is_enemy", _ENEMY_KEYS),
        ]
        if _matches_any(role_description, words)
    ]
    if (
        len(re.findall(_ORDINAL_PATTERN, description, re.I)) > 1
        or len(named_nodes) > 1
        or len(requested_roles) > 1
        or (
            named_nodes
            and any(not getattr(_semantic(named_nodes[0]), role) for role in requested_roles)
        )
    ):
        return TargetResolution(ambiguous=True, reason="unsupported_compound_selector")
    candidates: list[TargetCandidate] = []
    for node in nodes:
        sem = _semantic(node)
        if named_ids:
            if node.id not in named_ids:
                continue
        elif want_boss:
            if not sem.is_boss or sem.is_player:
                continue
        elif want_player:
            if not sem.is_player:
                continue
        elif want_enemy:
            if not (sem.is_enemy or sem.is_boss) or sem.is_player:
                continue
        else:
            continue
        if exclude_players and sem.is_player and not want_player and node.id not in named_ids:
            continue
        candidates.append(
            TargetCandidate(
                node_id=node.id,
                display_name=sem.display_name or getattr(node, "name", None),
                semantic=sem,
                score=1.0,
                reasons=["explicit name" if named_ids else "semantic role match"],
            )
        )

    resolution = TargetResolution(candidates=candidates)
    if not candidates:
        return resolution
    plural = re.search(
        r"所有|全部|每个|全体|\ball\b|\bevery\b|\bbosses\b|\benemies\b", description, re.I
    )
    if len(candidates) == 1 or plural:
        resolution.chosen = candidates[0]
        resolution.selected_ids = [candidate.node_id for candidate in candidates]
    else:
        resolution.ambiguous = True
        resolution.reason = "multiple_targets"
    return resolution


__all__ = ["TargetCandidate", "TargetResolution", "resolve_targets", "resolve_targets_grounded"]


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
    from udify.core.cognition.reference_spec import (
        OrderDomain,
        ReferenceOperator,
        ReferenceSpec,
    )
    from udify.core.cognition.reference_spec_resolver import (
        Success,
        resolve_reference,
    )

    base = resolve_targets(graph, description, exclude_players)
    if base.reason == "unsupported_compound_selector":
        return base
    ordinal_match = re.search(
        _ORDINAL_PATTERN,
        description,
        re.IGNORECASE,
    )
    superlative_match = re.search(
        r"最强|最弱|最高|最低|最多|最少|\b(?:weakest|strongest|highest|lowest|max|min)\b",
        description,
        re.IGNORECASE,
    )
    if not ordinal_match and not superlative_match:
        return base
    if not base.candidates:
        return base

    ordinal = None
    if ordinal_match:
        raw = ordinal_match.group(0).lower()
        numbers = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
            "first": 1,
            "second": 2,
            "third": 3,
            "fourth": 4,
            "fifth": 5,
        }
        if "last" in raw or "最后" in raw:
            ordinal = len(base.candidates)
        else:
            token = next(group for group in ordinal_match.groups() if group is not None)
            if token.isdigit():
                ordinal = int(token)
            elif token in numbers:
                ordinal = numbers[token]
            elif "十" in token:
                tens, units = token.split("十", 1)
                ordinal = numbers.get(tens, 1) * 10 + numbers.get(units, 0)
        if not ordinal or ordinal < 1:
            return TargetResolution(
                candidates=base.candidates, ambiguous=True, reason="unsupported_ordinal"
            )

    metric = "attack"
    if re.search(
        r"(?:血量|生命|hp)\s*(?:最[高低多少]|max|min)|(?:highest|lowest|max|min)\s*(?:hp|health)",
        description,
        re.I,
    ):
        metric = "hp"
    maximize = not bool(re.search(r"最弱|最低|最少|\b(?:weakest|lowest|min)\b", description, re.I))
    from udify.models.content_graph import ContentGraph

    selected_nodes = {candidate.node_id: candidate for candidate in base.candidates}
    normalized_nodes = []
    for node in graph.nodes:
        if node.id not in selected_nodes:
            continue
        sem = selected_nodes[node.id].semantic
        normalized_nodes.append(
            replace(node, properties={**node.properties, "hp": sem.hp, "attack": sem.attack})
        )

    operator = ReferenceOperator.ORDINAL if ordinal_match else ReferenceOperator.SUPERLATIVE
    spec = ReferenceSpec(
        operator=operator,
        ordinal=ordinal,
        metric=metric if superlative_match and not ordinal_match else None,
        maximize=maximize if superlative_match and not ordinal_match else None,
        order_domain=OrderDomain.DB_INDEX if ordinal_match else None,
    )
    result = resolve_reference(ContentGraph(nodes=normalized_nodes), spec)
    if isinstance(result, Success):
        resolved = result.reference
        resolved_node = next((n for n in graph.nodes if n.id == resolved.node_id), None)
        if resolved_node is None:
            base.ambiguous = True
            base.chosen = None
            return base
        sem = _semantic(resolved_node)
        chosen = TargetCandidate(
            node_id=resolved_node.id,
            display_name=resolved_node.name or None,
            semantic=sem,
            score=2.0,
            reasons=[
                f"grounded: {operator.value}",
                f"order_domain={resolved_node.properties.get('source_order_domain', 'db_index')}"
                if ordinal_match
                else f"metric={metric}, maximize={maximize}",
            ],
        )
        return TargetResolution(candidates=[chosen], chosen=chosen, ambiguous=False)
    base.ambiguous = True
    base.chosen = None
    base.selected_ids = []
    base.reason = "missing_or_ambiguous_reference_evidence"
    return base
