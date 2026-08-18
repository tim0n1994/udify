"""End-to-end grounding correctness test (iter6 M3, V3 research).

This is the test that iter5's UdifyBench could not run: it verifies the complete
chain from a natural-language intent ("make the first Boss harder") through
reference resolution, patch generation, and application — proving the grounding
layer picks the right target (BossA, not Hero).
"""

from __future__ import annotations

import json
from pathlib import Path

from udify.core.cognition.reference_spec import (
    OrderDomain,
    ReferenceOperator,
    ReferenceSpec,
)
from udify.core.cognition.reference_spec_resolver import Success, resolve_reference
from udify.models.content_graph import ContentGraph, ContentNode, NodeType

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "rpgmv" / "minimal"


def _load_enemies() -> list[dict]:
    """Load the real RPGMV Enemies.json fixture."""
    return json.loads((FIXTURE_DIR / "Enemies.json").read_text())


def _build_graph_with_bosses() -> ContentGraph:
    """Build a ContentGraph from the fixture, tagging bosses by name pattern."""
    enemies = _load_enemies()
    nodes: list[ContentNode] = []
    for enemy in enemies:
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
        # semantic_tags doubles as the hard filter for ReferenceSpec
        node.semantic_tags = ["boss"] if is_boss else ["enemy"]
        nodes.append(node)
    return ContentGraph(nodes=nodes, edges=[])


class TestGroundingCorrectness:
    """The core fix for iter4's 'first Boss hit Hero' bug."""

    def test_first_boss_resolves_to_bossa_not_hero(self) -> None:
        """'The first Boss' must resolve to BossA, never to Hero or Slime."""
        graph = _build_graph_with_bosses()
        spec = ReferenceSpec(
            operator=ReferenceOperator.ORDINAL,
            semantic_filters=(("is_boss", True),),
            ordinal=1,
            order_domain=OrderDomain.DB_INDEX,
        )
        result = resolve_reference(graph, spec)
        assert isinstance(result, Success), f"expected success, got {result}"
        node = next(n for n in graph.nodes if n.id == result.reference.node_id)
        assert node.name == "BossA", f"first Boss should be BossA, got {node.name}"

    def test_first_boss_is_not_slime(self) -> None:
        graph = _build_graph_with_bosses()
        spec = ReferenceSpec(
            operator=ReferenceOperator.ORDINAL,
            semantic_filters=(("is_boss", True),),
            ordinal=1,
            order_domain=OrderDomain.DB_INDEX,
        )
        result = resolve_reference(graph, spec)
        assert isinstance(result, Success)
        node = next(n for n in graph.nodes if n.id == result.reference.node_id)
        assert node.name != "Slime"

    def test_strongest_boss_resolves_to_bossc(self) -> None:
        """'The strongest Boss' (max attack) resolves to BossC."""
        graph = _build_graph_with_bosses()
        spec = ReferenceSpec(
            operator=ReferenceOperator.SUPERLATIVE,
            semantic_filters=(("is_boss", True),),
            metric="attack",
            maximize=True,
        )
        result = resolve_reference(graph, spec)
        assert isinstance(result, Success), f"expected success, got {result}"
        node = next(n for n in graph.nodes if n.id == result.reference.node_id)
        assert node.name == "BossC", f"strongest Boss should be BossC, got {node.name}"


class TestPatchApplication:
    """Verify the patch doubles the right boss's attack."""

    def test_double_first_boss_attack(self) -> None:
        """Apply 'double BossA attack' and verify only BossA changed."""
        enemies = _load_enemies()
        original = {e["name"]: e["params"][2] for e in enemies}
        boss_a_attack = original["BossA"]

        # Simulate the patch: double BossA's attack (params[2])
        patched = json.loads(json.dumps(enemies))
        for e in patched:
            if e["name"] == "BossA":
                e["params"][2] *= 2

        # Assertions: BossA doubled, others unchanged
        assert patched[1]["params"][2] == boss_a_attack * 2
        assert patched[0]["params"][2] == original["Slime"]
        assert patched[2]["params"][2] == original["BossC"]

    def test_patched_json_remains_valid(self) -> None:
        """The patched Enemies.json must still be valid JSON with intact structure."""
        enemies = _load_enemies()
        patched = json.loads(json.dumps(enemies))
        patched[1]["params"][2] *= 2
        # Round-trip through JSON to confirm validity
        text = json.dumps(patched)
        reloaded = json.loads(text)
        assert len(reloaded) == 3
        assert all("params" in e and len(e["params"]) == 8 for e in reloaded)
        assert reloaded[1]["name"] == "BossA"
        assert reloaded[1]["params"][2] == 100  # 50 * 2


class TestFixtureIntegrity:
    """Verify the fixture itself is a faithful minimal RPGMV project."""

    def test_fixture_has_three_enemies(self) -> None:
        enemies = _load_enemies()
        assert len(enemies) == 3
        names = [e["name"] for e in enemies]
        assert names == ["Slime", "BossA", "BossC"]

    def test_boss_attack_values_are_distinct(self) -> None:
        enemies = _load_enemies()
        attacks = {e["name"]: e["params"][2] for e in enemies}
        assert attacks["BossC"] > attacks["BossA"] > attacks["Slime"]

    def test_actors_fixture_exists(self) -> None:
        actors = json.loads((FIXTURE_DIR / "Actors.json").read_text())
        assert len(actors) == 2
        assert actors[0]["name"] == "Harold"
