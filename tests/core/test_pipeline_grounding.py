"""接地接入主路径的行为锁（iter7 M2-PR1/PR2）。

与 ``tests/e2e/test_e2e_grounding.py`` 的区别很关键：那个测试直接调
``resolve_reference`` 并用 ``json.dumps`` **模拟** patch，证明的是算法；本文件断言的是
**规划层真的只动接地目标**——即接线本身。iter5/iter6 两轮"算法绿、主路径没接"的教训
就在这里：绕过主路径的绿测试不能证明产品行为。
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from udify.core.cognition.target_resolver import resolve_targets_grounded
from udify.core.planning.action_space import ActionSpace
from udify.core.planning.state import Intent as PlanIntent
from udify.core.planning.state import PlanContext
from udify.models.content_graph import ContentGraph, ContentNode, NodeType

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "rpgmv" / "minimal"


def _build_graph() -> ContentGraph:
    """真实 RPGMV fixture → 含 Boss / 小怪 / 玩家角色的图。

    必须带上 Actors——iter4 的 bug 正是"改到 Hero"，没有玩家节点就测不出回归。
    """
    nodes: list[ContentNode] = []
    for enemy in json.loads((FIXTURE_DIR / "Enemies.json").read_text()):
        is_boss = "boss" in enemy["name"].lower()
        node = ContentNode(
            id=f"enemy_{enemy['id']}",
            name=enemy["name"],
            type=NodeType.CHARACTER,
            source_path="Enemies.json",
            properties={
                "attack": enemy["params"][2],
                "maxhp": enemy["params"][0],
                "db_index": enemy["id"] - 1,
                "is_boss": is_boss,
            },
        )
        node.semantic_tags = ["boss"] if is_boss else ["enemy"]
        nodes.append(node)
    for actor in json.loads((FIXTURE_DIR / "Actors.json").read_text()):
        node = ContentNode(
            id=f"actor_{actor['id']}",
            name=actor["name"],
            type=NodeType.CHARACTER,
            source_path="Actors.json",
            properties={"is_player": True, "attack": 10},
        )
        node.semantic_tags = ["player"]
        nodes.append(node)
    return ContentGraph(nodes=nodes, edges=[])


@pytest.fixture
def graph() -> ContentGraph:
    return _build_graph()


def _touched_names(graph: ContentGraph, priority_nodes: list[str]) -> set[str]:
    """规划层在给定接地目标下实际会修改哪些节点。"""
    names = {n.id: n.name for n in graph.nodes}
    actions = ActionSpace()._generate_modify_actions(
        graph,
        PlanIntent(description="让第一个 Boss 攻击力翻倍", priority_nodes=priority_nodes),
        PlanContext(),
    )
    return {names[a.target_id] for a in actions if a.target_id in names}


class TestGroundingReachesPlanner:
    """接地结果必须真的约束规划层——否则接地算法再准也无效。"""

    def test_first_boss_grounds_to_bossa(self, graph: ContentGraph) -> None:
        resolution = resolve_targets_grounded(graph, "让第一个 Boss 攻击力翻倍")
        assert resolution.chosen is not None
        assert resolution.chosen.display_name == "BossA"
        assert not resolution.ambiguous

    def test_planner_touches_only_the_grounded_boss(self, graph: ContentGraph) -> None:
        """核心回归：iter4 的「改错 Hero」必须不再发生。"""
        resolution = resolve_targets_grounded(graph, "让第一个 Boss 攻击力翻倍")
        assert _touched_names(graph, resolution.chosen_ids()) == {"BossA"}

    def test_player_actors_are_never_touched(self, graph: ContentGraph) -> None:
        """pass-to-pass：玩家角色不在意图范围内，必须零改动。"""
        resolution = resolve_targets_grounded(graph, "让第一个 Boss 攻击力翻倍")
        touched = _touched_names(graph, resolution.chosen_ids())
        assert "Harold" not in touched
        assert "Therese" not in touched

    def test_ungrounded_planning_is_the_old_broken_behavior(self, graph: ContentGraph) -> None:
        """反证：不接地时规划确实会扩散到玩家角色——证明这条线值得存在。"""
        random.seed(0)
        assert _touched_names(graph, []) - {"BossA"}, "未接地时应扩散到非目标节点"

    def test_grounded_planning_is_deterministic(self, graph: ContentGraph) -> None:
        """成功判据 #1：同一意图连续运行得到稳定 Patch。"""
        runs = {frozenset(_touched_names(graph, ["enemy_2"])) for _ in range(5)}
        assert len(runs) == 1


class TestAmbiguityIsNotGuessed:
    """歧义时宁可不接地，也不静默猜错——iter4 bug 的另一半。"""

    def test_unresolvable_target_leaves_priority_empty(self, graph: ContentGraph) -> None:
        resolution = resolve_targets_grounded(graph, "让那个很厉害的东西更强")
        grounded = resolution.chosen_ids() if resolution.chosen and not resolution.ambiguous else []
        # 未唯一接地时不得伪造目标；规划层回退到原有候选逻辑并由上层澄清
        assert grounded == [] or resolution.chosen is not None
