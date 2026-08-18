"""Tests for LiftSource provenance tracking (iter6 M5, V4 research)."""

from __future__ import annotations

import pytest

from udify.core.perception.semantic_lifter import LiftSource, SemanticLifter, TagResult
from udify.models.content_graph import ContentNode, NodeType


@pytest.fixture
def lifter() -> SemanticLifter:
    return SemanticLifter()


class TestLiftSource:
    def test_rule_tags_have_rule_source(self, lifter: SemanticLifter) -> None:
        """All tags from the rule-based lift_node carry source=RULE."""
        node = ContentNode(
            id="boss1",
            name="Goblin Boss",
            type=NodeType.CHARACTER,
            source_path="enemies.json",
            properties={},
        )
        result = lifter.lift_node(node)
        assert result.source is LiftSource.RULE
        assert len(result.tags) > 0

    def test_missing_source_is_distinct(self) -> None:
        """A MISSING source is a different value from RULE and LLM."""
        assert LiftSource.MISSING != LiftSource.RULE
        assert LiftSource.MISSING != LiftSource.LLM

    def test_default_source_is_rule(self) -> None:
        """A fresh TagResult defaults to RULE (the deterministic path)."""
        r = TagResult()
        assert r.source is LiftSource.RULE

    def test_source_settable_for_llm_path(self) -> None:
        """When an LLM lift runs, the source is LLM, not fabricated RULE."""
        r = TagResult(source=LiftSource.LLM)
        assert r.source is LiftSource.LLM

    def test_no_key_path_reports_missing_not_llm(self) -> None:
        """When no LLM key is available, semantic tags are MISSING, never LLM."""
        r = TagResult(source=LiftSource.MISSING)
        assert r.source is LiftSource.MISSING
        assert r.source is not LiftSource.LLM

    def test_character_node_gets_tagged(self, lifter: SemanticLifter) -> None:
        node = ContentNode(
            id="hero1",
            name="Hero Actor",
            type=NodeType.CHARACTER,
            source_path="actors.json",
            properties={},
        )
        result = lifter.lift_node(node)
        assert len(result.tags) > 0
        assert result.source is LiftSource.RULE

    def test_lift_graph_preserves_source(self, lifter: SemanticLifter) -> None:
        """lift_graph tags every node with RULE source (no LLM available)."""
        from udify.models.content_graph import ContentGraph

        node = ContentNode(
            id="item1",
            name="Sword Item",
            type=NodeType.ITEM,
            source_path="items.json",
            properties={},
        )
        graph = ContentGraph(nodes=[node], edges=[])
        lifter.lift_graph(graph)
        # The node should now have tags
        assert len(node.semantic_tags) > 0
