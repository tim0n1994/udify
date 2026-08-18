"""Mod dependency graph (DAG) and conflict detection (U5-MODSTACK-DEPENDENCY PR1).

DependencyGraph models which mods may coexist and in what install/uninstall
order. It gives a partial order; ModStack resolves the actual linear overlay
order for two mods that touch the same file despite having no dependency edge.

Core invariants (U5 research):
  - Each mod_id has at most one version in the active set.
  - Install order guarantees a dependency precedes its dependent.
  - Uninstall order guarantees a dependent precedes its dependency.
  - The active set is always acyclic, complete, and version-consistent.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class ConflictKind(StrEnum):
    CYCLE = "CYCLE"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    VERSION_CONFLICT = "VERSION_CONFLICT"


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """One mod's declared dependency on another."""

    mod_id: str
    depends_on: str
    version_constraint: str = ">=0"

    def to_dict(self) -> dict[str, object]:
        return {
            "mod_id": self.mod_id,
            "depends_on": self.depends_on,
            "version_constraint": self.version_constraint,
        }


@dataclass(frozen=True, slots=True)
class DependencyConflict:
    kind: ConflictKind
    mod_id: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind.value, "mod_id": self.mod_id, "detail": self.detail}


def _parse_constraint(constraint: str) -> tuple[str, float]:
    """Parse '>=1.0' into ('>=', 1.0). Defaults to ('>=', 0.0)."""
    for op in (">=", "<=", "==", ">", "<"):
        if constraint.startswith(op):
            try:
                return op, float(constraint[len(op) :])
            except ValueError:
                return op, 0.0
    return ">=", 0.0


@dataclass(frozen=True, slots=True)
class DependencyGraph:
    """A frozen DAG of mod dependency edges."""

    edges: tuple[DependencyEdge, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"edges": [e.to_dict() for e in self.edges]}

    def _relevant_edges(self, active: set[str]) -> list[DependencyEdge]:
        return [e for e in self.edges if e.mod_id in active]

    def _build_adj(self, active: set[str]) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {m: [] for m in active}
        for e in self._relevant_edges(active):
            adj.setdefault(e.mod_id, []).append(e.depends_on)
            adj.setdefault(e.depends_on, [])
        return adj

    def install_order(self, active: set[str]) -> list[str]:
        """Topological sort: dependencies before dependents.

        Raises ValueError if a cycle exists (call detect_conflicts first).
        """
        adj = self._build_adj(active)
        visited: set[str] = set()
        stack: set[str] = set()
        order: list[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in stack:
                raise ValueError(f"dependency cycle detected involving {node!r}")
            stack.add(node)
            for dep in adj.get(node, []):
                visit(dep)
            stack.discard(node)
            visited.add(node)
            order.append(node)

        for m in sorted(active):
            visit(m)
        return order

    def uninstall_order(self, active: set[str]) -> list[str]:
        """Reverse topological sort: dependents before dependencies."""
        return list(reversed(self.install_order(active)))

    def detect_conflicts(
        self,
        active: set[str],
        installed_versions: dict[str, str] | None = None,
    ) -> list[DependencyConflict]:
        """Detect cycles, missing dependencies, and version conflicts."""
        conflicts: list[DependencyConflict] = []
        versions = installed_versions or {}

        # Missing dependency.
        for e in self._relevant_edges(active):
            if e.depends_on not in active:
                conflicts.append(
                    DependencyConflict(
                        ConflictKind.MISSING_DEPENDENCY,
                        e.mod_id,
                        f"{e.mod_id} depends on {e.depends_on} which is not installed",
                    )
                )

        # Cycle.
        try:
            self.install_order(active)
        except ValueError as exc:
            conflicts.append(DependencyConflict(ConflictKind.CYCLE, "", str(exc)))

        # Version conflict.
        for e in self._relevant_edges(active):
            if e.depends_on in versions and e.mod_id in versions:
                op, required = _parse_constraint(e.version_constraint)
                try:
                    actual = float(versions[e.depends_on])
                except ValueError:
                    continue
                ok = (
                    (op == ">=" and actual >= required)
                    or (op == "<=" and actual <= required)
                    or (op == "==" and actual == required)
                    or (op == ">" and actual > required)
                    or (op == "<" and actual < required)
                )
                if not ok:
                    conflicts.append(
                        DependencyConflict(
                            ConflictKind.VERSION_CONFLICT,
                            e.mod_id,
                            f"{e.mod_id} requires {e.depends_on} {e.version_constraint} but {versions[e.depends_on]} is installed",
                        )
                    )
        return conflicts


def graph_from_manifests(manifests: Iterable[object]) -> DependencyGraph:
    """Build a DependencyGraph from a list of ModManifest records (iter5 U5 PR2).

    Each manifest's ``dependencies: list[str]`` becomes a DependencyEdge with a
    default ``>=0`` constraint (the manifest format carries mod IDs, not version
    constraints). This bridges the existing ModManifest schema to the new DAG
    without changing the manifest's persisted shape.
    """
    edges: list[DependencyEdge] = []
    for m in manifests:
        mod_id = getattr(m, "mod_id", "")
        for dep in getattr(m, "dependencies", []) or []:
            edges.append(DependencyEdge(mod_id=mod_id, depends_on=dep, version_constraint=">=0"))
    return DependencyGraph(tuple(edges))
