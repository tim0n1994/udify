"""ContentGraph 语义可观测性层测试（SEM-FIELD-01..03）。"""

from udify.models.content_graph import ContentNode, NodeType
from udify.models.semantic import (
    SEMANTIC_KEYS,
    SemanticView,
    get_semantic,
    set_semantic,
)


def _boss_node() -> ContentNode:
    return ContentNode(
        id="boss_01",
        type=NodeType.CHARACTER,
        name="暗影领主",
        properties={"is_boss": True, "is_player": False, "hp": 5000, "max_hp": 5000, "attack": 320},
    )


def _hero_node() -> ContentNode:
    return ContentNode(
        id="hero_01",
        type=NodeType.CHARACTER,
        name="勇者",
        properties={"is_player": True, "is_boss": False, "hp": 800, "attack": 120},
    )


def _plain_node() -> ContentNode:
    return ContentNode(id="item_01", type=NodeType.ITEM, name="药水", properties={})


def test_boss_view_is_boss_true() -> None:
    view = get_semantic(_boss_node())
    assert view.is_boss is True
    assert view.is_player is False
    assert view.hp == 5000
    assert view.attack == 320
    assert view.is_combatant() is True


def test_hero_view_is_player_true() -> None:
    view = get_semantic(_hero_node())
    assert view.is_player is True
    assert view.is_boss is False
    assert view.hp == 800
    assert view.is_combatant() is True


def test_plain_node_safe_defaults() -> None:
    view = get_semantic(_plain_node())
    # 安全默认值：不抛错，缺失字段为 False/None
    assert view.is_boss is False
    assert view.is_player is False
    assert view.hp is None
    assert view.is_combatant() is False


def test_boss_vs_hero_disambiguation() -> None:
    """意图接地的核心样例：is_boss=True 与 is_player=True 互斥。"""
    boss = get_semantic(_boss_node())
    hero = get_semantic(_hero_node())
    assert boss.is_boss and not boss.is_player
    assert hero.is_player and not hero.is_boss


def test_semantic_view_is_frozen() -> None:
    view = get_semantic(_boss_node())
    try:
        view.is_boss = False  # type: ignore[misc]
        raised = False
    except (AttributeError, Exception):
        raised = True
    assert raised, "SemanticView must be frozen"


def test_alias_tolerance() -> None:
    node = ContentNode(
        id="x",
        type=NodeType.CHARACTER,
        properties={"boss": "true", "HP": "999", "atk": 50},
    )
    view = get_semantic(node)
    assert view.is_boss is True
    assert view.hp == 999
    assert view.attack == 50


def test_set_semantic_roundtrip() -> None:
    node = _plain_node()
    set_semantic(node, is_boss=True, hp=100)
    view = get_semantic(node)
    assert view.is_boss is True
    assert view.hp == 100


def test_set_semantic_rejects_unknown_field() -> None:
    node = _plain_node()
    try:
        set_semantic(node, not_a_field=True)  # type: ignore[arg-type]
        raised = False
    except KeyError:
        raised = True
    assert raised


def test_semantic_keys_contract() -> None:
    # 契约稳定：约定键集合覆盖意图接地与探针所需
    for k in ["is_boss", "is_player", "is_enemy", "hp", "max_hp", "attack", "defense"]:
        assert k in SEMANTIC_KEYS


def test_default_view() -> None:
    v = SemanticView()
    assert v.is_boss is False
    assert v.hp is None
