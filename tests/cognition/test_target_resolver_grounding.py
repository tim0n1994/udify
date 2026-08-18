"""Integration test: grounded target resolution fixes the 'first Boss' bug (U1 PR2)."""

from __future__ import annotations

from udify.core.cognition.target_resolver import resolve_targets_grounded
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


def _graph_with_bosses():
    g = ContentGraph()
    for i, name in enumerate(["BossA", "BossB", "BossC"]):
        g.nodes.append(
            ContentNode(
                id=f"b{i}",
                type=NodeType.RESOURCE,
                name=name,
                properties={"is_boss": True, "db_index": i, "attack": 100 + i * 50, "hp": 500},
            )
        )
    return g


def test_first_boss_resolves_uniquely_not_ambiguous():
    """The iter4 bug: 'first Boss' hit Hero. Now it resolves to the first Boss uniquely."""
    g = _graph_with_bosses()
    r = resolve_targets_grounded(g, "让第一个 Boss 更难")
    assert r.chosen is not None
    assert r.chosen.display_name == "BossA"
    assert r.ambiguous is False


def test_strongest_boss_resolves_by_attack():
    g = _graph_with_bosses()
    r = resolve_targets_grounded(g, "最强的 Boss")
    assert r.chosen is not None
    assert r.chosen.display_name == "BossC"  # attack=200


def test_non_ordinal_falls_back_to_plain_resolver():
    g = _graph_with_bosses()
    r = resolve_targets_grounded(g, "所有 Boss")
    # No ordinal/superlative -> plain resolve_targets (may be ambiguous with 3 bosses)
    assert len(r.candidates) >= 1


def test_player_excluded_by_default():
    g = _graph_with_bosses()
    g.nodes.append(
        ContentNode(id="hero", type=NodeType.RESOURCE, name="Hero", properties={"is_player": True})
    )
    r = resolve_targets_grounded(g, "让第一个 Boss 更难")
    assert r.chosen is not None
    assert r.chosen.display_name == "BossA"
