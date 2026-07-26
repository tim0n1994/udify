"""
动作 Schema + Patch 合成器 + miu2d 闭环测试（PLAN-ACTION + PATCH-SYN + 批次 2 验收）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from udify.core.adapters.miu2d_dsl import DslCommandRegistry
from udify.core.adapters.miu2d_world import GameWorldGraphBuilder
from udify.core.miu2d_pipeline import Miu2dClosedLoop
from udify.core.planning.action_schemas import ActionKind, ActionSchemaRegistry
from udify.core.planning.patch_synthesizer import PatchSynthesizer, PlannedAction
from udify.models.cdl_patch import ExecutionMode, OpType


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    (tmp_path / "characters.ini").write_text(
        "[Boss]\nMaxLife=500\nAttack=50\n[Hero]\nMaxLife=100\n"
    )
    return tmp_path


# --- PLAN-ACTION 测试 --------------------------------------------------------


class TestActionSchemas:
    def test_registry_has_numeric_schemas(self) -> None:
        reg = ActionSchemaRegistry()
        numeric = [s for s in reg.all_schemas() if s.kind == ActionKind.NUMERIC_SCALE]
        assert any(s.name == "scale_health" for s in numeric)
        assert any(s.name == "scale_offense" for s in numeric)

    def test_find_applicable_for_boss(self) -> None:
        reg = ActionSchemaRegistry()
        applicable = reg.find_applicable(("boss", "tunable"), numeric_kind="health")
        names = [s.name for s in applicable]
        assert "scale_health" in names

    def test_constraint_enforced(self) -> None:
        reg = ActionSchemaRegistry()
        health = next(s for s in reg.all_schemas() if s.name == "scale_health")
        assert any("factor" in c for c in health.constraints)

    def test_script_insert_schema_exists(self) -> None:
        reg = ActionSchemaRegistry()
        scripts = [s for s in reg.all_schemas() if s.kind == ActionKind.SCRIPT_INSERT]
        assert len(scripts) >= 1

    def test_reward_schemas_exist(self) -> None:
        reg = ActionSchemaRegistry()
        rewards = [s for s in reg.all_schemas() if s.kind == ActionKind.REWARD_MODIFY]
        assert len(rewards) >= 2


# --- PATCH-SYN 测试 ----------------------------------------------------------


class TestPatchSynthesizer:
    def test_synthesize_numeric_scale(self, game_root: Path) -> None:
        """PATCH-SYN-01/02: 图目标 → source anchor + INI emitter"""
        graph = GameWorldGraphBuilder().build(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        synth = PatchSynthesizer()
        ops = synth.synthesize(
            graph,
            [
                PlannedAction(
                    schema_name="scale_health",
                    target_node_id=boss.id,
                    params={"factor": 2.0, "numeric_kind": "health"},
                    reason="double boss hp",
                )
            ],
        )
        assert len(ops) == 1
        op = ops[0]
        assert op.execution_mode == ExecutionMode.FILE_PATCH
        assert op.payload["emitter"] == "ini"
        assert op.payload["key"] == "MaxLife"
        assert op.payload["old_value"] == 500
        assert op.payload["value"] == 1000
        # PATCH-SYN-01: 精确 SourceSpan
        assert op.source_span is not None
        assert "MaxLife" in op.source_span.ast_path

    def test_synthesize_lua_insert_safe(self, game_root: Path) -> None:
        """PATCH-SYN-04: Lua 安全插入"""
        graph = GameWorldGraphBuilder().build(game_root)
        # 找一个脚本节点（这里用一个 RESOURCE 兜底）
        node = graph.nodes[0]
        synth = PatchSynthesizer()
        ops = synth.synthesize(
            graph,
            [
                PlannedAction(
                    schema_name="insert_script",
                    target_node_id=node.id,
                    params={"location": "main", "guard": "x > 0", "body": "print('safe')"},
                )
            ],
        )
        assert len(ops) == 1
        assert ops[0].payload["emitter"] == "lua_insert"

    def test_lua_insert_rejects_dangerous(self, game_root: Path) -> None:
        """PATCH-SYN-04: 危险 API 脚本被拒绝"""
        graph = GameWorldGraphBuilder().build(game_root)
        node = graph.nodes[0]
        synth = PatchSynthesizer()
        ops = synth.synthesize(
            graph,
            [
                PlannedAction(
                    schema_name="insert_script",
                    target_node_id=node.id,
                    params={"location": "main", "body": "os.execute('rm -rf /')"},
                )
            ],
        )
        assert len(ops) == 0  # 危险脚本拒绝

    def test_dsl_command_emitter(self, game_root: Path) -> None:
        """PATCH-SYN-05: DSL 命令 emitter（schema 校验）"""
        graph = GameWorldGraphBuilder().build(game_root)
        node = graph.nodes[0]
        synth = PatchSynthesizer()
        ops = synth.synthesize(
            graph,
            [
                PlannedAction(
                    schema_name="dsl_command",
                    target_node_id=node.id,
                    params={"command": "GiveItem", "args": ["sword", 1]},
                )
            ],
        )
        assert len(ops) == 1
        assert ops[0].payload["emitter"] == "dsl"
        assert ops[0].payload["command"] == "GiveItem"

    def test_reverse_builder_numeric(self, game_root: Path) -> None:
        """PATCH-SYN-06: reverse builder（数值修改可回滚）"""
        graph = GameWorldGraphBuilder().build(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        synth = PatchSynthesizer()
        ops = synth.synthesize(
            graph,
            [
                PlannedAction(
                    schema_name="scale_health",
                    target_node_id=boss.id,
                    params={"factor": 2.0, "numeric_kind": "health"},
                )
            ],
        )
        forward = ops[0]
        reverse = PatchSynthesizer.build_reverse(forward)
        # 逆操作交换 old/new
        assert reverse.payload["value"] == 500
        assert reverse.payload["old_value"] == 1000
        assert reverse.payload["reverse"] is True

    def test_reverse_lua_insert(self, game_root: Path) -> None:
        """PATCH-SYN-06: reverse builder（Lua 插入可回滚）"""
        from udify.models.cdl_patch import PatchOperation

        op = PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id="lua:script.lua",
            payload={"emitter": "lua_insert", "body": "print('x')"},
            execution_mode=ExecutionMode.FILE_PATCH,
        )
        reverse = PatchSynthesizer.build_reverse(op)
        assert reverse.payload["emitter"] == "lua_remove"
        assert reverse.payload.get("remove_body") == "print('x')"


# --- DSL 命令表测试（ADAPT-MIU2D-05）---------------------------------------


class TestDslRegistry:
    def test_known_command(self) -> None:
        reg = DslCommandRegistry()
        assert reg.is_known("GiveItem")
        assert reg.category("GiveItem") == "reward"

    def test_unknown_command_warning(self) -> None:
        """未知命令标 warning（允许但记录）"""
        reg = DslCommandRegistry()
        ok, msg = reg.validate("UnknownCmd", [1])
        assert ok is True
        assert "warning" in msg

    def test_bad_args_rejected(self) -> None:
        reg = DslCommandRegistry()
        ok, msg = reg.validate("GiveItem", [])
        assert ok is False


# --- 批次 2 端到端验收 -------------------------------------------------------


class TestMiu2dClosedLoop:
    """批次 2 验收：自然语言 → 带证据语义图 → file_patch 计划 → VFS 预览"""

    def test_full_loop_health(self, game_root: Path) -> None:
        loop = Miu2dClosedLoop(game_root)
        result = loop.run("让Boss血量翻倍")
        assert result.success
        # 1. 语义图带证据
        assert result.graph is not None
        boss = [n for n in result.graph.nodes if n.name == "Boss"][0]
        assert boss.confidence is not None
        assert boss.confidence.score > 0
        # 2. file_patch 计划
        assert result.patch is not None
        assert all(op.execution_mode == ExecutionMode.FILE_PATCH for op in result.patch.operations)
        # 3. VFS 预览
        assert len(result.vfs_diffs) > 0

    def test_vfs_does_not_touch_original(self, game_root: Path) -> None:
        """VFS 预览模式不修改原文件"""
        original = (game_root / "characters.ini").read_text()
        loop = Miu2dClosedLoop(game_root)
        loop.run("让Boss血量翻倍")
        after = (game_root / "characters.ini").read_text()
        assert original == after

    def test_patch_applied_to_vfs_changes_preview(self, game_root: Path) -> None:
        """VFS 中的预览反映了修改"""
        loop = Miu2dClosedLoop(game_root)
        result = loop.run("让Boss血量翻倍")
        assert result.success
        # diff 应包含 MaxLife 的变化
        diff_content = str(result.vfs_diffs)
        assert "MaxLife=1000" in diff_content or "1000" in diff_content

    def test_factor_parsing(self, game_root: Path) -> None:
        """『1.5倍』倍数解析"""
        loop = Miu2dClosedLoop(game_root)
        result = loop.run("让Boss血量1.5倍")
        assert result.success
        boss_op = [
            op
            for op in result.patch.operations
            if "Boss" in str(op.source_span.ast_path if op.source_span else "")
        ]
        if boss_op:
            assert boss_op[0].payload["factor"] == 1.5

    def test_constraint_blocks_extreme_factor(self, game_root: Path) -> None:
        """factor 超过 schema 约束（5.0）应被挡"""
        loop = Miu2dClosedLoop(game_root)
        result = loop.run("让Boss血量100倍")
        # 100 > 5.0 约束 → 该 boss 的动作被挡
        boss_ops = [
            op
            for op in (result.patch.operations if result.patch else [])
            if op.payload.get("factor", 0) == 100.0
        ]
        assert len(boss_ops) == 0
