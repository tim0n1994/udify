"""Tests for mod dependency graph (U5-MODSTACK-DEPENDENCY PR1)."""

from __future__ import annotations

import pytest

from udify.core.mod_manager.dependency_graph import (
    ConflictKind,
    DependencyEdge,
    DependencyGraph,
)


def test_install_order_dependencies_first():
    g = DependencyGraph((DependencyEdge("B", "A"), DependencyEdge("C", "B")))
    order = g.install_order({"A", "B", "C"})
    assert order.index("A") < order.index("B") < order.index("C")


def test_uninstall_order_reverse():
    g = DependencyGraph((DependencyEdge("B", "A"),))
    order = g.uninstall_order({"A", "B"})
    assert order.index("B") < order.index("A")


def test_cycle_detected():
    g = DependencyGraph((DependencyEdge("A", "B"), DependencyEdge("B", "A")))
    conflicts = g.detect_conflicts({"A", "B"})
    assert any(c.kind is ConflictKind.CYCLE for c in conflicts)


def test_missing_dependency_detected():
    g = DependencyGraph((DependencyEdge("B", "A"),))
    conflicts = g.detect_conflicts({"B"})
    assert any(c.kind is ConflictKind.MISSING_DEPENDENCY for c in conflicts)


def test_version_conflict_detected():
    g = DependencyGraph((DependencyEdge("B", "A", ">=2.0"),))
    conflicts = g.detect_conflicts({"A", "B"}, installed_versions={"A": "1.0", "B": "1.0"})
    assert any(c.kind is ConflictKind.VERSION_CONFLICT for c in conflicts)


def test_version_satisfied_no_conflict():
    g = DependencyGraph((DependencyEdge("B", "A", ">=2.0"),))
    conflicts = g.detect_conflicts({"A", "B"}, installed_versions={"A": "2.5", "B": "1.0"})
    assert not [c for c in conflicts if c.kind is ConflictKind.VERSION_CONFLICT]


def test_empty_graph_install_order():
    assert DependencyGraph().install_order({"A", "B"}) == ["A", "B"]


def test_graph_is_frozen():
    g = DependencyGraph(())
    with pytest.raises(AttributeError):
        g.edges = (DependencyEdge("X", "Y"),)  # type: ignore[misc]


def test_to_dict_structure():
    g = DependencyGraph((DependencyEdge("B", "A"),))
    d = g.to_dict()
    assert d["edges"][0]["mod_id"] == "B"
