"""Deterministic reference resolution over a Udify content graph."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from udify.core.cognition.reference_spec import (
    ClarificationReason,
    ClarificationRequest,
    OrderDomain,
    ReferenceOperator,
    ReferenceSpec,
    ScalarValue,
)
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    """Immutable identity of one resolved content node."""

    node_id: str
    name: str
    node_type: NodeType

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type.name,
        }


@dataclass(frozen=True, slots=True)
class Success:
    """Successful unique resolution result."""

    reference: ResolvedReference

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "status": "success",
            "reference": self.reference.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class NeedsClarification:
    """Resolution result requiring explicit user disambiguation."""

    request: ClarificationRequest

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "status": "needs_clarification",
            "request": self.request.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Failed:
    """Resolution result for a deterministic terminal failure."""

    reason: ClarificationReason

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "status": "failed",
            "reason": self.reason.value,
        }


type ResolveResult = Success | NeedsClarification | Failed


@dataclass(frozen=True, slots=True)
class _SemanticView:
    is_boss: bool
    hp: float | None
    attack: float | None
    defense: float | None


@dataclass(frozen=True, slots=True)
class _Candidate:
    node: ContentNode
    node_type: NodeType
    attributes: Mapping[str, object]
    semantic: _SemanticView


_ORDER_KEYS: Mapping[OrderDomain, str] = {
    OrderDomain.DB_INDEX: "db_index",
    OrderDomain.TROOP_MEMBER: "troop_member_index",
    OrderDomain.FIRST_ENCOUNTER: "first_encounter_index",
    OrderDomain.SPATIAL: "distance_to_player",
}


def resolve_reference(
    graph: ContentGraph,
    spec: ReferenceSpec,
) -> ResolveResult:
    """Resolve one reference specification against a content graph.

    The resolver is intentionally deterministic. It performs semantic hard
    filtering first, applies exactly one ordering or comparison operation, and
    returns success only when the legal solution set contains one node.

    Args:
        graph: Content graph whose nodes are candidate targets.
        spec: Immutable deterministic resolution specification.

    Returns:
        ``Success`` for one unique target, ``NeedsClarification`` for an
        ambiguous or incomplete comparison, or ``Failed`` when no candidates
        satisfy the hard filters.
    """
    candidates = _filter_candidates(graph, spec)
    if not candidates:
        return Failed(ClarificationReason.NO_CANDIDATES)

    if spec.operator is ReferenceOperator.ID:
        return _resolve_id(candidates, spec)
    if spec.operator is ReferenceOperator.ORDINAL:
        return _resolve_ordinal(candidates, spec)
    if spec.operator is ReferenceOperator.SUPERLATIVE:
        return _resolve_superlative(candidates, spec)
    return _resolve_spatial(candidates, spec)


def _filter_candidates(
    graph: ContentGraph,
    spec: ReferenceSpec,
) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []

    for node in graph.nodes:
        candidate = _candidate_from_node(node)

        if spec.node_type is not None and candidate.node_type is not spec.node_type:
            continue
        if spec.name is not None and node.name.casefold() != spec.name.casefold():
            continue
        if spec.operator is ReferenceOperator.ID and node.id != spec.identifier:
            continue
        if not _matches_filters(candidate, spec.semantic_filters):
            continue

        candidates.append(candidate)

    return tuple(candidates)


def _candidate_from_node(node: ContentNode) -> _Candidate:
    attributes = _node_attributes(node)
    semantic = _SemanticView(
        is_boss=_boolean_attribute(
            attributes,
            "is_boss",
            default=False,
        ),
        hp=_numeric_attribute(attributes, "hp"),
        attack=_numeric_attribute(attributes, "attack"),
        defense=_numeric_attribute(attributes, "defense"),
    )

    return _Candidate(
        node=node,
        node_type=_node_type(node),
        attributes=attributes,
        semantic=semantic,
    )


def _node_attributes(node: ContentNode) -> Mapping[str, object]:
    raw_attributes = _compat_field(
        node,
        "attributes",
        "properties",
    )
    if isinstance(raw_attributes, Mapping):
        return cast(Mapping[str, object], raw_attributes)
    return {}


def _node_type(node: ContentNode) -> NodeType:
    raw_node_type = _compat_field(
        node,
        "node_type",
        "type",
    )
    if isinstance(raw_node_type, NodeType):
        return raw_node_type
    raise TypeError(f"content node {node.id!r} has no valid NodeType field")


def _compat_field(
    node: ContentNode,
    primary: str,
    fallback: str,
) -> object:
    for field_name in (primary, fallback):
        try:
            return object.__getattribute__(node, field_name)
        except AttributeError:
            continue
    return None


def _matches_filters(
    candidate: _Candidate,
    semantic_filters: Sequence[tuple[str, ScalarValue]],
) -> bool:
    for key, expected in semantic_filters:
        if key == "is_boss":
            actual: object = candidate.semantic.is_boss
        elif key == "hp":
            actual = candidate.semantic.hp
        elif key == "attack":
            actual = candidate.semantic.attack
        elif key == "defense":
            actual = candidate.semantic.defense
        else:
            actual = candidate.attributes.get(key)

        if actual != expected:
            return False

    return True


def _resolve_id(
    candidates: Sequence[_Candidate],
    spec: ReferenceSpec,
) -> ResolveResult:
    if len(candidates) == 1:
        return Success(_to_reference(candidates[0]))

    return NeedsClarification(
        ClarificationRequest(
            reason=ClarificationReason.AMBIGUOUS_ORDINAL,
            question=(f"节点 ID {spec.identifier!r} 对应多个候选，请检查内容图。"),
            candidate_ids=_candidate_ids(candidates),
        )
    )


def _resolve_ordinal(
    candidates: Sequence[_Candidate],
    spec: ReferenceSpec,
) -> ResolveResult:
    if spec.order_domain is None:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MISSING_ORDER_DOMAIN,
                question=("序数指代必须明确数据库、队伍、首次遭遇或空间顺序。"),
                candidate_ids=_candidate_ids(candidates),
                options=tuple(domain.value for domain in OrderDomain),
            )
        )

    attribute_name = _ORDER_KEYS[spec.order_domain]
    ranked: list[tuple[tuple[float, ...], _Candidate]] = []
    missing_ids: list[str] = []

    for candidate in candidates:
        key = _order_key(candidate.attributes.get(attribute_name))
        if key is None:
            missing_ids.append(candidate.node.id)
        else:
            ranked.append((key, candidate))

    if missing_ids:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MISSING_ORDER_DOMAIN,
                question=(f"部分候选缺少顺序字段 {attribute_name!r}，不能安全计算序数目标。"),
                candidate_ids=tuple(missing_ids),
                details=(("order_domain", spec.order_domain.value),),
            )
        )

    ranked.sort(key=lambda item: item[0])

    assert spec.ordinal is not None
    target_index = spec.ordinal - 1

    if target_index >= len(ranked):
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.AMBIGUOUS_ORDINAL,
                question=(f"只有 {len(ranked)} 个候选，无法选择第 {spec.ordinal} 个。"),
                candidate_ids=_candidate_ids(candidates),
                details=(("ordinal", spec.ordinal),),
            )
        )

    target_key, target = ranked[target_index]
    tied = tuple(candidate for key, candidate in ranked if key == target_key)

    if len(tied) != 1:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.AMBIGUOUS_ORDINAL,
                question=(f"第 {spec.ordinal} 个位置存在并列候选，不能静默按节点 ID 选择。"),
                candidate_ids=_candidate_ids(tied),
                details=(("order_domain", spec.order_domain.value),),
            )
        )

    return Success(_to_reference(target))


def _resolve_superlative(
    candidates: Sequence[_Candidate],
    spec: ReferenceSpec,
) -> ResolveResult:
    assert spec.metric is not None

    values: list[tuple[float, _Candidate]] = []
    missing_ids: list[str] = []

    for candidate in candidates:
        value = _semantic_metric(
            candidate.semantic,
            spec.metric,
        )
        if value is None:
            missing_ids.append(candidate.node.id)
        else:
            values.append((value, candidate))

    if missing_ids:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MULTI_SUPERLATIVE_TIE,
                question=(f"部分候选缺少 {spec.metric!r}，不能证明全局最高或最低。"),
                candidate_ids=tuple(missing_ids),
                details=(("metric", spec.metric),),
            )
        )

    maximize = True if spec.maximize is None else spec.maximize
    selected_value = (
        max(value for value, _candidate in values)
        if maximize
        else min(value for value, _candidate in values)
    )

    tied = tuple(candidate for value, candidate in values if value == selected_value)

    if len(tied) != 1:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MULTI_SUPERLATIVE_TIE,
                question=(f"多个候选在 {spec.metric!r} 上并列。"),
                candidate_ids=_candidate_ids(tied),
                details=(
                    ("metric", spec.metric),
                    ("value", selected_value),
                ),
            )
        )

    return Success(_to_reference(tied[0]))


def _resolve_spatial(
    candidates: Sequence[_Candidate],
    spec: ReferenceSpec,
) -> ResolveResult:
    values: list[tuple[float, _Candidate]] = []
    missing_ids: list[str] = []

    for candidate in candidates:
        value = _numeric_value(candidate.attributes.get("distance_to_player"))
        if value is None:
            missing_ids.append(candidate.node.id)
        else:
            values.append((value, candidate))

    if missing_ids:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MISSING_ORDER_DOMAIN,
                question=("部分候选缺少 'distance_to_player'，不能安全计算空间目标。"),
                candidate_ids=tuple(missing_ids),
                details=(
                    (
                        "order_domain",
                        OrderDomain.SPATIAL.value,
                    ),
                ),
            )
        )

    maximize = False if spec.maximize is None else spec.maximize
    selected_value = (
        max(value for value, _candidate in values)
        if maximize
        else min(value for value, _candidate in values)
    )

    tied = tuple(candidate for value, candidate in values if value == selected_value)

    if len(tied) != 1:
        return NeedsClarification(
            ClarificationRequest(
                reason=ClarificationReason.MULTI_SUPERLATIVE_TIE,
                question="多个候选与玩家的空间距离并列。",
                candidate_ids=_candidate_ids(tied),
                details=(
                    (
                        "order_domain",
                        OrderDomain.SPATIAL.value,
                    ),
                    ("distance", selected_value),
                ),
            )
        )

    return Success(_to_reference(tied[0]))


def _semantic_metric(
    view: _SemanticView,
    metric: str,
) -> float | None:
    if metric == "attack":
        return view.attack
    if metric == "hp":
        return view.hp
    raise ValueError(f"unsupported metric: {metric}")


def _boolean_attribute(
    attributes: Mapping[str, object],
    key: str,
    *,
    default: bool,
) -> bool:
    value = attributes.get(key)
    return value if isinstance(value, bool) else default


def _numeric_attribute(
    attributes: Mapping[str, object],
    key: str,
) -> float | None:
    return _numeric_value(attributes.get(key))


def _numeric_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(
        value,
        int | float,
    ):
        return None

    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _order_key(value: object) -> tuple[float, ...] | None:
    scalar = _numeric_value(value)
    if scalar is not None:
        return (scalar,)

    if isinstance(value, str) or not isinstance(
        value,
        Sequence,
    ):
        return None

    key: list[float] = []
    for item in value:
        numeric = _numeric_value(item)
        if numeric is None:
            return None
        key.append(numeric)

    return tuple(key) if key else None


def _candidate_ids(
    candidates: Sequence[_Candidate],
) -> tuple[str, ...]:
    return tuple(candidate.node.id for candidate in candidates)


def _to_reference(
    candidate: _Candidate,
) -> ResolvedReference:
    return ResolvedReference(
        node_id=candidate.node.id,
        name=candidate.node.name,
        node_type=candidate.node_type,
    )
