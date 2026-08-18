"""目标节点解析测试（COG-LLM-01 / Reference Resolution）。

核心样例：Boss 翻倍不误伤 Hero。
"""

from udify.core.cognition.target_resolver import resolve_targets
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


def _boss() -> ContentNode:
    return ContentNode(
        id="boss_01",
        type=NodeType.CHARACTER,
        name="暗影领主",
        properties={"is_boss": True, "is_player": False, "hp": 5000, "display_name": "暗影领主"},
    )


def _hero() -> ContentNode:
    return ContentNode(
        id="hero_01",
        type=NodeType.CHARACTER,
        name="勇者",
        properties={"is_player": True, "is_boss": False, "hp": 800, "display_name": "勇者"},
    )


def _enemy() -> ContentNode:
    return ContentNode(
        id="goblin_01",
        type=NodeType.CHARACTER,
        name="哥布林",
        properties={"is_enemy": True, "hp": 120},
    )


def _graph(*nodes):
    g = ContentGraph()
    for n in nodes:
        g.add_node(n)
    return g


def test_boss_doubled_does_not_hit_hero():
    g = _graph(_boss(), _hero())
    res = resolve_targets(g, "把 Boss 的血量翻倍")
    assert res.chosen is not None
    assert res.chosen.node_id == "boss_01"
    assert res.chosen.node_id != "hero_01"
    assert res.chosen.semantic.is_boss is True


def test_hero_excluded_by_default():
    g = _graph(_boss(), _hero())
    res = resolve_targets(g, "把 Boss 血量翻倍")
    ids = [c.node_id for c in res.candidates]
    assert "hero_01" not in ids, "Hero must be excluded to prevent misfire"


def test_enemy_keyword_matches_enemy_and_boss():
    g = _graph(_boss(), _enemy(), _hero())
    res = resolve_targets(g, "所有敌人")
    ids = {c.node_id for c in res.candidates}
    assert "boss_01" in ids
    assert "goblin_01" in ids
    assert "hero_01" not in ids


def test_no_match_returns_empty():
    g = _graph(_hero())
    res = resolve_targets(g, "把 Boss 血量翻倍")
    assert res.chosen is None
    assert res.candidates == []


def test_explicit_player_target():
    g = _graph(_boss(), _hero())
    res = resolve_targets(g, "主角", exclude_players=False)
    ids = [c.node_id for c in res.candidates]
    assert "hero_01" in ids


def test_high_hp_boosts_score():
    g = _graph(
        ContentNode(id="wb", type=NodeType.CHARACTER, properties={"is_boss": True, "hp": 50000}),
        ContentNode(id="sb", type=NodeType.CHARACTER, properties={"is_boss": True, "hp": 500}),
    )
    res = resolve_targets(g, "Boss")
    assert res.chosen is not None
    assert res.chosen.node_id == "wb"


def test_ambiguous_flag_when_tie():
    g = _graph(
        ContentNode(id="b1", type=NodeType.CHARACTER, properties={"is_boss": True, "hp": 5000}),
        ContentNode(id="b2", type=NodeType.CHARACTER, properties={"is_boss": True, "hp": 5000}),
    )
    res = resolve_targets(g, "Boss")
    assert res.ambiguous is True
