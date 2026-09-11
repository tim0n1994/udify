from pathlib import Path

import pytest

from udify.core.cognition.target_resolver import resolve_targets_grounded
from udify.core.miu2d_pipeline import IntentClarification, Miu2dClosedLoop
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


@pytest.fixture
def loop(tmp_path: Path) -> Miu2dClosedLoop:
    (tmp_path / "characters.ini").write_text(
        "[BossA]\nMaxLife=500\nAttack=50\nDefense=20\n"
        "[BossB]\nMaxLife=900\nAttack=90\nDefense=40\n"
        "[Hero]\nMaxLife=100\nAttack=15\nDefense=10\n",
        encoding="utf-8",
    )
    (tmp_path / "items.ini").write_text(
        "[Potion]\nType=heal\nValue=50\nPrice=20\n", encoding="utf-8"
    )
    return Miu2dClosedLoop(tmp_path)


@pytest.mark.parametrize(
    ("intent", "names"),
    [
        ("把 BossA 的血量翻倍", {"BossA"}),
        ("把 Hero 的血量翻倍", {"Hero"}),
        ("所有 Boss 血量翻倍", {"BossA", "BossB"}),
        ("double all bosses hp", {"BossA", "BossB"}),
        ("最强 Boss 血量翻倍", {"BossB"}),
        ("最弱 Boss 血量翻倍", {"BossA"}),
        ("Boss HP最高的血量翻倍", {"BossB"}),
        ("第一个 Boss 血量翻倍", {"BossA"}),
        ("第二个 Boss 血量翻倍", {"BossB"}),
        ("最后一个 Boss 血量翻倍", {"BossB"}),
    ],
)
def test_targets_only_match_intent(loop: Miu2dClosedLoop, intent: str, names: set[str]) -> None:
    graph = loop.perceive()
    actions, patch, errors = loop.plan(graph, intent)
    by_id = {node.id: node.name for node in graph.nodes}
    assert not errors and patch is not None
    assert {by_id[action.target_node_id] for action in actions} == names
    vfs, errors, fatal = loop.preview(patch)
    assert not errors and fatal is None
    if "Hero" not in names:
        assert "MaxLife=100" in vfs.read_file("characters.ini")


def test_ambiguous_role_requires_selection(loop: Miu2dClosedLoop) -> None:
    graph = loop.perceive()
    with pytest.raises(IntentClarification) as exc:
        loop.plan(graph, "Boss 血量翻倍")
    assert {item["display_name"] for item in exc.value.candidates} == {"BossA", "BossB"}
    assert exc.value.question and exc.value.reason
    selected = exc.value.candidates[1]["node_id"]
    actions, patch, _ = loop.plan(graph, "Boss 血量翻倍", target_ids=[selected])
    assert patch is not None
    assert [action.target_node_id for action in actions] == [selected]


def test_selection_cannot_expand_role_scope(loop: Miu2dClosedLoop) -> None:
    graph = loop.perceive()
    hero = next(node for node in graph.nodes if node.name == "Hero")
    with pytest.raises(IntentClarification):
        loop.plan(graph, "Boss 血量翻倍", target_ids=[hero.id])


@pytest.mark.parametrize("intent", ["血量翻倍", "BossA 血量提高", "BossA 血量翻倍，攻击减半"])
def test_incomplete_numeric_instruction_is_not_guessed(loop: Miu2dClosedLoop, intent: str) -> None:
    with pytest.raises(IntentClarification):
        loop.plan(loop.perceive(), intent)


@pytest.mark.parametrize(
    "intent", ["BossA 不要改血量，攻击翻倍", "BossA do not change HP, attack x2"]
)
def test_negated_field_is_never_mutated(loop: Miu2dClosedLoop, intent: str) -> None:
    graph = loop.perceive()
    actions, patch, _ = loop.plan(graph, intent)
    assert patch is not None
    assert {action.schema_name for action in actions} == {"scale_offense"}
    assert {action.params["factor"] for action in actions} == {2.0}
    assert {op.payload["key"] for op in patch.operations} == {"Attack"}


def _ordered_graph() -> ContentGraph:
    return ContentGraph(
        nodes=[
            ContentNode(
                id=name,
                name=name,
                type=NodeType.CHARACTER,
                properties={"is_boss": True, "db_index": order, "attack": attack, "hp": hp},
            )
            for name, order, attack, hp in [
                ("BossC", 8, 30, 700),
                ("BossA", 2, 10, 900),
                ("BossB", 5, 20, 500),
            ]
        ]
    )


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ("第二个 Boss", "BossB"),
        ("third Boss", "BossC"),
        ("最后一个 Boss", "BossC"),
        ("weakest Boss", "BossA"),
        ("Boss 血量最高", "BossA"),
        ("Boss hp最低", "BossB"),
    ],
)
def test_grounded_operator_uses_explicit_evidence(intent: str, expected: str) -> None:
    result = resolve_targets_grounded(_ordered_graph(), intent)
    assert result.chosen is not None and not result.ambiguous
    assert result.chosen.node_id == expected


def test_missing_order_and_tied_metric_need_clarification() -> None:
    graph = _ordered_graph()
    for node in graph.nodes:
        node.properties.pop("db_index")
        node.properties["attack"] = 10
    for intent in ["第二个 Boss", "最后一个 Boss", "最强 Boss"]:
        result = resolve_targets_grounded(graph, intent)
        assert result.ambiguous and result.chosen is None


@pytest.mark.parametrize(
    "intent",
    [
        "BossA 血量 -2倍",
        "BossA 血量翻倍，然后删除 Hero",
        "BossA hp x2 and delete Hero",
        "BossA 血量增加2倍",
    ],
)
def test_unsupported_numeric_clauses_do_not_partially_apply(
    loop: Miu2dClosedLoop, intent: str
) -> None:
    with pytest.raises(IntentClarification):
        loop.plan(loop.perceive(), intent)


@pytest.mark.parametrize(
    "intent",
    [
        "所有 Boss 血量翻倍，不要改 BossA",
        "所有 Boss 除了 BossA 血量翻倍",
        "double all bosses hp except BossA",
        "all bosses hp x2, do not change BossA",
        "所有 Boss 血量翻倍，BossA 保持不变",
        "所有 Boss 血量翻倍，BossA 不要改",
    ],
)
def test_target_exclusions_are_not_silently_discarded(loop: Miu2dClosedLoop, intent: str) -> None:
    with pytest.raises(IntentClarification) as exc:
        loop.plan(loop.perceive(), intent)
    assert exc.value.reason == "unsupported_target_exclusion"


def test_hp_comparison_can_select_target_for_attack_change(loop: Miu2dClosedLoop) -> None:
    graph = loop.perceive()
    actions, patch, _ = loop.plan(graph, "血量最高的 Boss 攻击翻倍")
    assert patch is not None
    assert [graph.get_node(action.target_node_id).name for action in actions] == ["BossB"]
    assert {op.payload["key"] for op in patch.operations} == {"Attack"}


def test_source_order_is_recorded_and_not_node_iteration_order(loop: Miu2dClosedLoop) -> None:
    graph = loop.perceive()
    graph.nodes.reverse()
    actions, _, _ = loop.plan(graph, "第一个 Boss 血量翻倍")
    node = graph.get_node(actions[0].target_node_id)
    assert node.name == "BossA"
    assert node.properties["db_index"] == [0, 0]
    assert "relative_path_then_ini_section" in actions[0].reason


@pytest.mark.parametrize("intent", ["提高Boss掉落率", "削弱治疗道具效果"])
def test_old_underspecified_golden_intents_require_clarification(
    loop: Miu2dClosedLoop, intent: str
) -> None:
    with pytest.raises(IntentClarification):
        loop.plan(loop.perceive(), intent)


def test_explicit_potion_reduction_has_exact_value(loop: Miu2dClosedLoop) -> None:
    actions, patch, errors = loop.plan(loop.perceive(), "Potion Value 减半")
    assert patch is not None and not errors
    assert len(actions) == 1 and len(patch.operations) == 1
    assert patch.operations[0].payload["key"] == "Value"
    assert patch.operations[0].payload["old_value"] == 50
    assert patch.operations[0].payload["value"] == 25


@pytest.mark.parametrize("intent", ["BossB 攻击翻倍", "所有 Boss 攻击翻倍"])
def test_missing_requested_field_never_falls_back_or_partially_applies(
    loop: Miu2dClosedLoop, intent: str
) -> None:
    graph = loop.perceive()
    next(node for node in graph.nodes if node.name == "BossB").properties.pop("Attack")
    with pytest.raises(IntentClarification) as exc:
        loop.plan(graph, intent)
    assert exc.value.reason == "missing_numeric_property"


@pytest.mark.parametrize(
    "intent", ["所有 Boss 血量翻倍，不要改血量", "所有 Boss 血量翻倍，BossA 不要改血量"]
)
def test_conflicting_preservation_constraint_blocks_patch(
    loop: Miu2dClosedLoop, intent: str
) -> None:
    with pytest.raises(IntentClarification):
        loop.plan(loop.perceive(), intent)


@pytest.mark.parametrize(
    "intent",
    [
        "第一个和第二个 Boss 血量翻倍",
        "第一个与最后一个 Boss 血量翻倍",
        "所有 Boss 和玩家血量翻倍",
        "first and second Boss hp x2",
        "all bosses and players hp x2",
        "BossA and Hero hp x2",
    ],
)
def test_compound_selectors_are_not_truncated(loop: Miu2dClosedLoop, intent: str) -> None:
    graph = loop.perceive()
    with pytest.raises(IntentClarification) as exc:
        loop.plan(graph, intent)
    assert exc.value.reason == "unsupported_compound_selector"
    boss = next(node for node in graph.nodes if node.name == "BossA")
    with pytest.raises(IntentClarification) as selected:
        loop.plan(graph, intent, target_ids=[boss.id])
    assert selected.value.reason == "unsupported_compound_selector"


@pytest.mark.parametrize("description", ["first and second Boss", "所有 Boss 和玩家"])
def test_resolver_rejects_union_before_resolving_first_branch(description: str) -> None:
    resolution = resolve_targets_grounded(_ordered_graph(), description)
    assert resolution.ambiguous and resolution.chosen_ids() == []
    assert resolution.reason == "unsupported_compound_selector"


def test_nonboss_hp_is_not_a_role_match() -> None:
    graph = _ordered_graph()
    graph.nodes.append(
        ContentNode(
            id="enemy",
            name="Slime",
            type=NodeType.CHARACTER,
            properties={"hp": 99999, "is_enemy": True},
        )
    )
    result = resolve_targets_grounded(graph, "Boss")
    assert {item.node_id for item in result.candidates} == {"BossA", "BossB", "BossC"}
    assert result.ambiguous and result.chosen is None
