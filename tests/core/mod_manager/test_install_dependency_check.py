"""Tests for DAG-aware dependency conflict checking (iter6 M2, PR3)."""

from __future__ import annotations

import pytest

from udify.core.mod_manager.dependency_graph import ConflictKind
from udify.core.mod_manager.mod_exporter import ModManifest
from udify.core.mod_manager.mod_manager import MultiModManager


@pytest.fixture
def manager(tmp_path) -> MultiModManager:
    return MultiModManager(str(tmp_path))


def _manifest(mod_id: str, deps: list[str] | None = None) -> ModManifest:
    return ModManifest(
        mod_id=mod_id,
        name=mod_id,
        version="1.0",
        author="test",
        dependencies=deps or [],
    )


class TestCheckDependencyConflicts:
    @pytest.mark.asyncio
    async def test_no_conflicts_clean_install(self, manager: MultiModManager) -> None:
        await manager.install_mod("base", "Base", "1.0", "test", ["file1"])
        conflicts = manager.check_dependency_conflicts(_manifest("addon", ["base"]))
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_missing_dependency_detected(self, manager: MultiModManager) -> None:
        await manager.install_mod("base", "Base", "1.0", "test", ["file1"])
        # addon depends on 'missing_mod' which is not installed
        conflicts = manager.check_dependency_conflicts(_manifest("addon", ["missing_mod"]))
        kinds = [c.kind for c in conflicts]
        assert ConflictKind.MISSING_DEPENDENCY in kinds

    @pytest.mark.asyncio
    async def test_cycle_detected(self, manager: MultiModManager) -> None:
        await manager.install_mod("a", "A", "1.0", "test", ["fa"], dependencies=["b"])
        # candidate b depends on a -> cycle a->b->a
        conflicts = manager.check_dependency_conflicts(_manifest("b", ["a"]))
        # The dependency graph builder detects cycles via topological sort
        # Either CYCLE or the detect_conflicts surfaces it
        assert len(conflicts) > 0

    @pytest.mark.asyncio
    async def test_satisfied_dependency_no_conflict(self, manager: MultiModManager) -> None:
        await manager.install_mod("base", "Base", "1.0", "test", ["f1"])
        await manager.install_mod("mid", "Mid", "1.0", "test", ["f2"], dependencies=["base"])
        # addon depends on mid (which depends on base) — both installed, no conflict
        conflicts = manager.check_dependency_conflicts(_manifest("addon", ["mid"]))
        assert conflicts == []
