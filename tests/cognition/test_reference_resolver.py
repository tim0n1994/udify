from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import Any, cast

import pytest

from udify.core.cognition.reference_spec import (
    ClarificationReason,
    ClarificationRequest,
    OrderDomain,
    ReferenceOperator,
    ReferenceSpec,
)
from udify.core.cognition.reference_spec_resolver import (
    Failed,
    NeedsClarification,
    ResolvedReference,
    Success,
    resolve_reference,
)
from udify.models.content_graph import (
    ContentGraph,
    ContentNode,
    NodeType,
)


def _node(
    node_id: str,
    name: str,
    attributes: dict[str, object],
    *,
    node_type: NodeType = NodeType.CHARACTER,
) -> ContentNode:
    field_names = {field.name for field in fields(ContentNode)}
    kwargs: dict[str, object] = {
        "id": node_id,
        "name": name,
    }

    if "node_type" in field_names:
        kwargs["node_type"] = node_type
    else:
        kwargs["type"] = node_type

    if "attributes" in field_names:
        kwargs["attributes"] = attributes
    else:
        kwargs["properties"] = attributes

    constructor = cast(Any, ContentNode)
    return cast(ContentNode, constructor(**kwargs))


def _graph(*nodes: ContentNode) -> ContentGraph:
    return ContentGraph(nodes=list(nodes))


def _boss(
    node_id: str,
    *,
    name: str | None = None,
    db_index: int | None = None,
    troop_member_index: int | tuple[int, ...] | None = None,
    first_encounter_index: int | tuple[int, ...] | None = None,
    distance_to_player: float | None = None,
    hp: int | None = None,
    attack: int | None = None,
    node_type: NodeType = NodeType.CHARACTER,
) -> ContentNode:
    attributes: dict[str, object] = {
        "is_boss": True,
    }
    optional_values: dict[str, object | None] = {
        "db_index": db_index,
        "troop_member_index": troop_member_index,
        "first_encounter_index": first_encounter_index,
        "distance_to_player": distance_to_player,
        "hp": hp,
        "attack": attack,
    }
    attributes.update({key: value for key, value in optional_values.items() if value is not None})

    return _node(
        node_id,
        name or node_id,
        attributes,
        node_type=node_type,
    )


def _ordinal(
    domain: OrderDomain | None,
    ordinal: int = 1,
) -> ReferenceSpec:
    return ReferenceSpec(
        operator=ReferenceOperator.ORDINAL,
        semantic_filters=(("is_boss", True),),
        ordinal=ordinal,
        order_domain=domain,
    )


def test_reference_spec_is_frozen() -> None:
    spec = _ordinal(OrderDomain.DB_INDEX)

    with pytest.raises(FrozenInstanceError):
        spec.ordinal = 2  # type: ignore[misc]


def test_clarification_request_is_frozen() -> None:
    request = ClarificationRequest(
        reason=ClarificationReason.AMBIGUOUS_ORDINAL,
        question="Which Boss?",
    )

    with pytest.raises(FrozenInstanceError):
        request.question = "Changed"  # type: ignore[misc]


def test_reference_spec_to_dict_round_trip() -> None:
    spec = ReferenceSpec(
        operator=ReferenceOperator.ORDINAL,
        semantic_filters=(
            ("is_boss", True),
            ("phase", "late"),
        ),
        node_type=NodeType.CHARACTER,
        name="Dragon",
        ordinal=2,
        order_domain=OrderDomain.FIRST_ENCOUNTER,
    )

    assert ReferenceSpec.from_dict(spec.to_dict()) == spec


def test_clarification_request_to_dict_round_trip() -> None:
    request = ClarificationRequest(
        reason=ClarificationReason.MULTI_SUPERLATIVE_TIE,
        question="Choose one",
        candidate_ids=("enemy:1", "enemy:2"),
        options=("enemy:1", "enemy:2"),
        details=(("metric", "attack"),),
    )

    assert ClarificationRequest.from_dict(request.to_dict()) == request


def test_invalid_zero_ordinal_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="ordinal >= 1",
    ):
        _ordinal(
            OrderDomain.DB_INDEX,
            ordinal=0,
        )


def test_invalid_superlative_metric_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="attack.*hp",
    ):
        ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            metric="defense",
        )


def test_id_operator_resolves_exact_node_id() -> None:
    graph = _graph(
        _boss("enemy:1"),
        _boss("enemy:2"),
    )

    result = resolve_reference(
        graph,
        ReferenceSpec(
            operator=ReferenceOperator.ID,
            identifier="enemy:2",
        ),
    )

    assert result == Success(
        ResolvedReference(
            "enemy:2",
            "enemy:2",
            NodeType.CHARACTER,
        )
    )


def test_id_operator_returns_failed_when_missing() -> None:
    result = resolve_reference(
        _graph(_boss("enemy:1")),
        ReferenceSpec(
            operator=ReferenceOperator.ID,
            identifier="enemy:404",
        ),
    )

    assert result == Failed(ClarificationReason.NO_CANDIDATES)


def test_first_boss_uses_db_index_not_graph_order() -> None:
    hero = _node(
        "actor:1",
        "Hero",
        {
            "is_boss": False,
            "db_index": -1,
            "attack": 9999,
        },
    )
    later = _boss(
        "enemy:20",
        db_index=20,
    )
    first = _boss(
        "enemy:10",
        db_index=0,
    )

    result = resolve_reference(
        _graph(hero, later, first),
        _ordinal(OrderDomain.DB_INDEX),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:10"


def test_second_boss_uses_db_index() -> None:
    result = resolve_reference(
        _graph(
            _boss("enemy:5", db_index=5),
            _boss("enemy:1", db_index=1),
            _boss("enemy:3", db_index=3),
        ),
        _ordinal(
            OrderDomain.DB_INDEX,
            ordinal=2,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:3"


def test_ordinal_without_order_domain_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                db_index=0,
            )
        ),
        _ordinal(None),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MISSING_ORDER_DOMAIN
    assert set(result.request.options) == {domain.value for domain in OrderDomain}


def test_missing_db_index_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                db_index=0,
            ),
            _boss("enemy:2"),
        ),
        _ordinal(OrderDomain.DB_INDEX),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MISSING_ORDER_DOMAIN
    assert result.request.candidate_ids == ("enemy:2",)


def test_duplicate_ordinal_rank_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                db_index=0,
            ),
            _boss(
                "enemy:2",
                db_index=0,
            ),
        ),
        _ordinal(OrderDomain.DB_INDEX),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.AMBIGUOUS_ORDINAL
    assert result.request.candidate_ids == (
        "enemy:1",
        "enemy:2",
    )


def test_ordinal_out_of_range_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                db_index=0,
            )
        ),
        _ordinal(
            OrderDomain.DB_INDEX,
            ordinal=2,
        ),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.AMBIGUOUS_ORDINAL


def test_troop_member_domain_uses_compound_order_key() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:2",
                troop_member_index=(2, 0),
            ),
            _boss(
                "enemy:1",
                troop_member_index=(1, 1),
            ),
        ),
        _ordinal(OrderDomain.TROOP_MEMBER),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:1"


def test_first_encounter_domain_uses_encounter_index() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:2",
                first_encounter_index=(2, 0, 0),
            ),
            _boss(
                "enemy:1",
                first_encounter_index=(1, 3, 0),
            ),
        ),
        _ordinal(OrderDomain.FIRST_ENCOUNTER),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:1"


def test_spatial_order_domain_supports_nth_nearest() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                distance_to_player=3.0,
            ),
            _boss(
                "enemy:2",
                distance_to_player=1.0,
            ),
            _boss(
                "enemy:3",
                distance_to_player=2.0,
            ),
        ),
        _ordinal(
            OrderDomain.SPATIAL,
            ordinal=2,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:3"


def test_superlative_max_attack_selects_strongest_boss() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                attack=80,
            ),
            _boss(
                "enemy:2",
                attack=120,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            semantic_filters=(("is_boss", True),),
            metric="attack",
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:2"


def test_superlative_min_hp_selects_smallest_hp() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                hp=500,
            ),
            _boss(
                "enemy:2",
                hp=200,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            semantic_filters=(("is_boss", True),),
            metric="hp",
            maximize=False,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:2"


def test_superlative_tie_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                attack=100,
            ),
            _boss(
                "enemy:2",
                attack=100,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            semantic_filters=(("is_boss", True),),
            metric="attack",
        ),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MULTI_SUPERLATIVE_TIE


def test_superlative_missing_metric_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                attack=100,
            ),
            _boss("enemy:2"),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            semantic_filters=(("is_boss", True),),
            metric="attack",
        ),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MULTI_SUPERLATIVE_TIE
    assert result.request.candidate_ids == ("enemy:2",)


def test_spatial_operator_selects_nearest_by_default() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                distance_to_player=5.0,
            ),
            _boss(
                "enemy:2",
                distance_to_player=2.0,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SPATIAL,
            semantic_filters=(("is_boss", True),),
            order_domain=OrderDomain.SPATIAL,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:2"


def test_spatial_operator_can_select_farthest() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                distance_to_player=5.0,
            ),
            _boss(
                "enemy:2",
                distance_to_player=2.0,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SPATIAL,
            semantic_filters=(("is_boss", True),),
            maximize=True,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:1"


def test_spatial_tie_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                distance_to_player=2.0,
            ),
            _boss(
                "enemy:2",
                distance_to_player=2.0,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SPATIAL,
            semantic_filters=(("is_boss", True),),
        ),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MULTI_SUPERLATIVE_TIE


def test_spatial_missing_distance_requests_clarification() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                distance_to_player=2.0,
            ),
            _boss("enemy:2"),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.SPATIAL,
            semantic_filters=(("is_boss", True),),
        ),
    )

    assert isinstance(result, NeedsClarification)
    assert result.request.reason is ClarificationReason.MISSING_ORDER_DOMAIN


def test_zero_boss_candidates_returns_failed() -> None:
    hero = _node(
        "actor:1",
        "Hero",
        {
            "is_boss": False,
            "db_index": 0,
        },
    )

    result = resolve_reference(
        _graph(hero),
        _ordinal(OrderDomain.DB_INDEX),
    )

    assert result == Failed(ClarificationReason.NO_CANDIDATES)


def test_node_type_filter_is_hard_constraint() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "event:1",
                db_index=0,
                node_type=NodeType.EVENT,
            ),
            _boss(
                "enemy:1",
                db_index=1,
                node_type=NodeType.CHARACTER,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.ORDINAL,
            semantic_filters=(("is_boss", True),),
            node_type=NodeType.CHARACTER,
            ordinal=1,
            order_domain=OrderDomain.DB_INDEX,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:1"


def test_name_filter_is_case_insensitive_exact_match() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                name="Dragon",
                db_index=0,
            ),
            _boss(
                "enemy:2",
                name="Dragonling",
                db_index=1,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.ORDINAL,
            semantic_filters=(("is_boss", True),),
            name="dragon",
            ordinal=1,
            order_domain=OrderDomain.DB_INDEX,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:1"


def test_semantic_numeric_filter_is_applied_before_sorting() -> None:
    result = resolve_reference(
        _graph(
            _boss(
                "enemy:1",
                hp=100,
                db_index=0,
            ),
            _boss(
                "enemy:2",
                hp=200,
                db_index=1,
            ),
        ),
        ReferenceSpec(
            operator=ReferenceOperator.ORDINAL,
            semantic_filters=(
                ("is_boss", True),
                ("hp", 200.0),
            ),
            ordinal=1,
            order_domain=OrderDomain.DB_INDEX,
        ),
    )

    assert isinstance(result, Success)
    assert result.reference.node_id == "enemy:2"


def test_success_to_dict() -> None:
    result = Success(
        ResolvedReference(
            "enemy:1",
            "Boss",
            NodeType.CHARACTER,
        )
    )

    assert result.to_dict() == {
        "status": "success",
        "reference": {
            "node_id": "enemy:1",
            "name": "Boss",
            "node_type": "CHARACTER",
        },
    }


def test_needs_clarification_to_dict() -> None:
    result = NeedsClarification(
        ClarificationRequest(
            reason=ClarificationReason.AMBIGUOUS_ORDINAL,
            question="Choose",
            candidate_ids=("enemy:1",),
        )
    )

    assert result.to_dict()["status"] == "needs_clarification"
    assert result.to_dict()["request"] == result.request.to_dict()


def test_failed_to_dict() -> None:
    assert Failed(ClarificationReason.NO_CANDIDATES).to_dict() == {
        "status": "failed",
        "reason": "no_candidates",
    }
