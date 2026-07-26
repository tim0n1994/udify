"""
miu2d 适配器测试（ADAPT-ENGINE-01..04, ADAPT-MIU2D-01）。

覆盖：
- detect：签名文件 → 置信度
- perceive：复用现有 parser，节点带 SourceSpan
- get_action_schemas / emit_patch（file_patch）
- build_runtime_probes
- EngineAdapter 协议一致性（契约测试）
- package_mod 产物

对应 ITERATION-PLAN-2026-07.md §4.2。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from udify.core.adapters import EngineAdapter, Miu2dAdapter
from udify.models.cdl_patch import ExecutionMode


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    """构造一个最小 miu2d 样例游戏目录"""
    (tmp_path / "characters.ini").write_text("[Boss]\nMaxLife=500\nAttack=50\n")
    (tmp_path / "items.ini").write_text("[Sword]\nAttack=20\n")
    return tmp_path


@pytest.fixture
def adapter() -> Miu2dAdapter:
    return Miu2dAdapter()


class TestDetection:
    def test_detect_miu2d_signatures(self, adapter: Miu2dAdapter, game_root: Path) -> None:
        result = adapter.detect(game_root)
        assert result.engine_id == "miu2d"
        assert result.confidence.score > 0
        assert any("characters.ini" in e for e in result.evidence)

    def test_detect_empty_dir_low_confidence(self, adapter: Miu2dAdapter, tmp_path: Path) -> None:
        result = adapter.detect(tmp_path)
        assert result.confidence.score == 0.0


class TestPerceive:
    def test_perceive_produces_spans(self, adapter: Miu2dAdapter, game_root: Path) -> None:
        graph = adapter.perceive(game_root)
        assert len(graph.nodes) > 0
        # 每个 CHARACTER 节点应有 SourceSpan + confidence
        for node in graph.nodes:
            if node.name in ("Boss", "Sword"):
                assert node.source_span is not None  # type: ignore[attr-defined]
                assert node.source_span.file_path.endswith(".ini")  # type: ignore[attr-defined]
                assert node.confidence is not None
                assert node.confidence.score > 0

    def test_perceives_boss_properties(self, adapter: Miu2dAdapter, game_root: Path) -> None:
        graph = adapter.perceive(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"]
        assert boss
        assert boss[0].properties.get("MaxLife") == 500


class TestActionSchemasAndPatch:
    def test_get_action_schemas(self, adapter: Miu2dAdapter) -> None:
        schemas = adapter.get_action_schemas()
        assert len(schemas) >= 1
        assert all("execution_mode" in s for s in schemas)

    def test_emit_patch_file_patch_mode(self, adapter: Miu2dAdapter, game_root: Path) -> None:
        graph = adapter.perceive(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        ops = adapter.emit_patch(
            graph,
            [
                {
                    "action": "modify_property",
                    "target_id": boss.id,
                    "key": "MaxLife",
                    "value": 1000,
                    "file_path": "characters.ini",
                    "reason": "double boss hp",
                }
            ],
        )
        assert len(ops) == 1
        assert ops[0].execution_mode == ExecutionMode.FILE_PATCH
        assert ops[0].planning_reason == "double boss hp"
        assert ops[0].source_span is not None


class TestRuntimeProbes:
    def test_build_probes_for_characters(self, adapter: Miu2dAdapter, game_root: Path) -> None:
        graph = adapter.perceive(game_root)
        probes = adapter.build_runtime_probes(graph)
        # 至少为 Boss 生成一个探针
        assert len(probes) >= 1
        assert all(p["status"] == "suggested" for p in probes)


class TestPackage:
    def test_package_mod_writes_manifest(
        self, adapter: Miu2dAdapter, game_root: Path, tmp_path: Path
    ) -> None:
        graph = adapter.perceive(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        ops = adapter.emit_patch(
            graph,
            [
                {
                    "action": "modify_property",
                    "target_id": boss.id,
                    "key": "MaxLife",
                    "value": 1000,
                    "file_path": "characters.ini",
                }
            ],
        )
        out_dir = tmp_path / "out"
        result = adapter.package_mod(graph, ops, out_dir)
        assert result.exists()
        manifest = json.loads(result.read_text())
        assert manifest["engine"] == "miu2d"
        assert len(manifest["operations"]) == 1
        assert "graph_checksum" in manifest


class TestProtocolConformance:
    """契约测试：miu2d adapter 满足 EngineAdapter 协议（ADAPT-ENGINE-04）"""

    def test_is_engine_adapter(self, adapter: Miu2dAdapter) -> None:
        # runtime_checkable Protocol：结构匹配即可
        assert isinstance(adapter, EngineAdapter)

    def test_engine_id_property(self, adapter: Miu2dAdapter) -> None:
        assert adapter.engine_id == "miu2d"
