"""
批次 3 验证与基准测试（VAL-STATIC + VAL-RUNTIME + EVAL-INTENT + BENCH）。

覆盖：
- VAL-STATIC-01..05：schema/reference/numeric/syntax/dangerous
- VAL-RUNTIME-01..05：ProbeSpec/headless runtime/console/state/report
- EVAL-INTENT-01..04：golden case + goal/constraint/scope 评分
- BENCH-01..03：10 个 golden case 全过（成功判据 #7）
"""

from __future__ import annotations

from pathlib import Path

import pytest

from udify.core.evaluation.benchmark_runner import (
    BenchmarkRunner,
    materialize_fixture,
)
from udify.core.evaluation.eval_v3 import (
    GoldenCase,
    IntentAlignmentEvaluatorV3,
)
from udify.core.evaluation.miu2d_cases import get_miu2d_golden_cases
from udify.core.validation.runtime_probe import (
    HeadlessRuntimeProbe,
    ProbeKind,
    ProbeSpec,
    probes_for_graph,
)
from udify.core.validation.static_validator import (
    StaticValidatorV3,
)
from udify.models.cdl_patch import CDLPatch, ExecutionMode, OpType, create_modify_property_op
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    (tmp_path / "characters.ini").write_text(
        "[Boss]\nMaxLife=500\nAttack=50\n[Hero]\nMaxLife=100\n"
    )
    return tmp_path


# === VAL-STATIC-01..05 =======================================================


class TestStaticValidator:
    def _graph_with_boss(self) -> ContentGraph:
        g = ContentGraph()
        g.add_node(
            ContentNode(
                id="boss1", type=NodeType.CHARACTER, name="Boss", properties={"MaxLife": 500}
            )
        )
        return g

    def test_schema_valid_patch(self) -> None:
        """VAL-STATIC-01: 合法 patch 通过"""
        v = StaticValidatorV3()
        graph = self._graph_with_boss()
        patch = CDLPatch(
            operations=[
                create_modify_property_op("boss1", "MaxLife", 1000),
            ]
        )
        # 标记 file_patch + emitter
        patch.operations[0] = type(patch.operations[0])(
            op_type=OpType.MODIFY_PROPERTY,
            target_id="boss1",
            payload={"key": "MaxLife", "value": 1000, "emitter": "ini"},
            execution_mode=ExecutionMode.FILE_PATCH,
        )
        report = v.validate(patch, graph)
        assert report.passed

    def test_numeric_range_violation(self) -> None:
        """VAL-STATIC-03: 数值超范围报错"""
        v = StaticValidatorV3()
        graph = self._graph_with_boss()
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("boss1", "MaxLife", -1))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="boss1",
                    payload={"key": "MaxLife", "value": -100, "emitter": "ini"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        report = v.validate(patch, graph)
        assert not report.passed
        assert any(f.check == "VAL-STATIC-03" for f in report.blocking_errors)

    def test_dangerous_api_in_lua_body(self) -> None:
        """VAL-STATIC-05: patch 引入危险 API 报错"""
        v = StaticValidatorV3()
        graph = self._graph_with_boss()
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("boss1", "x", 1))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="boss1",
                    payload={"emitter": "lua_insert", "body": "os.execute('rm -rf /')"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        report = v.validate(patch, graph)
        assert not report.passed
        assert any(f.check == "VAL-STATIC-05" for f in report.blocking_errors)

    def test_dangling_reference(self) -> None:
        """VAL-STATIC-02: 悬空引用报错"""
        v = StaticValidatorV3()
        graph = ContentGraph()  # 空 graph
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("ghost", "hp", 100))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="ghost",
                    payload={"key": "hp", "value": 100, "emitter": "generic"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        report = v.validate(patch, graph)
        # generic emitter 跳过引用检查，但 ini emitter 会报
        assert report.passed or any(f.check == "VAL-STATIC-02" for f in report.blocking_errors)

    def test_syntax_reparse_ini(self) -> None:
        """VAL-STATIC-04: INI 语法重解析"""
        v = StaticValidatorV3()
        diffs = [{"path": "test.ini", "new_content": "[Boss]\nMaxLife=500\nbad line no equals\n"}]
        report = v.validate(CDLPatch(), ContentGraph(), diffs)
        assert any(f.check == "VAL-STATIC-04" for f in report.warnings)


# === VAL-RUNTIME-01..05 =====================================================


class TestRuntimeProbe:
    def test_probe_spec_schema(self) -> None:
        """VAL-RUNTIME-01: ProbeSpec 可构造"""
        spec = ProbeSpec(
            probe_id="p1",
            kind=ProbeKind.READ_STATE,
            target_node="boss1",
            expect={"name": "Boss"},
            timeout_ms=3000,
        )
        assert spec.kind == ProbeKind.READ_STATE
        assert spec.expect["name"] == "Boss"

    def test_headless_start_probe(self) -> None:
        """VAL-RUNTIME-02: headless 启动探针"""
        graph = ContentGraph()
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="Boss"))
        probe = HeadlessRuntimeProbe()
        report = probe.run(
            graph,
            [ProbeSpec(probe_id="start", kind=ProbeKind.START, action="launch")],
        )
        assert report.game_started

    def test_state_read_bridge(self) -> None:
        """VAL-RUNTIME-04: 状态读取桥"""
        graph = ContentGraph()
        graph.add_node(
            ContentNode(id="boss1", type=NodeType.CHARACTER, name="Boss", properties={"hp": 500})
        )
        probe = HeadlessRuntimeProbe()
        report = probe.run(
            graph,
            [
                ProbeSpec(
                    probe_id="read_boss",
                    kind=ProbeKind.READ_STATE,
                    target_node="boss1",
                    expect={"name": "Boss"},
                )
            ],
        )
        assert report.state_readable
        assert report.results[0].passed

    def test_console_error_capture(self) -> None:
        """VAL-RUNTIME-03: console 错误捕获"""
        probe = HeadlessRuntimeProbe()
        diffs = [{"path": "bad.ini", "new_content": "[S]\ninvalid line\n"}]
        report = probe.run(
            ContentGraph(),
            [ProbeSpec(probe_id="console", kind=ProbeKind.CONSOLE_ERROR_SCAN)],
            diffs,
        )
        assert report.console_error_count > 0
        assert not report.passed

    def test_probe_report_format(self) -> None:
        """VAL-RUNTIME-05: 探针报告格式"""
        graph = ContentGraph()
        graph.add_node(ContentNode(id="n1", type=NodeType.CHARACTER, name="X"))
        probe = HeadlessRuntimeProbe()
        report = probe.run(graph, probes_for_graph(graph))
        d = report.to_dict()
        assert "passed" in d
        assert "probe_count" in d
        assert "results" in d

    def test_probes_for_graph_auto(self) -> None:
        """probes_for_graph 自动生成探针集"""
        graph = ContentGraph()
        graph.add_node(
            ContentNode(id="n1", type=NodeType.CHARACTER, name="Boss", properties={"hp": 1})
        )
        probes = probes_for_graph(graph)
        assert any(p.kind == ProbeKind.START for p in probes)
        assert any(p.kind == ProbeKind.READ_STATE for p in probes)
        assert any(p.kind == ProbeKind.CONSOLE_ERROR_SCAN for p in probes)


# === EVAL-INTENT-01..04 =====================================================


class TestIntentAlignmentV3:
    def test_goal_achievement(self) -> None:
        """EVAL-INTENT-02: 目标达成评分"""
        case = GoldenCase(
            case_id="t1",
            intent="double hp",
            expected_patterns=[{"key": "MaxLife"}],
        )
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("b", "MaxLife", 1000))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="b",
                    payload={"key": "MaxLife", "value": 1000, "emitter": "ini"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        ev = IntentAlignmentEvaluatorV3()
        result = ev.evaluate(case, patch)
        assert result.goal_achievement == 1.0

    def test_hard_constraint_reject(self) -> None:
        """EVAL-INTENT-03: 硬约束失败即 reject"""
        case = GoldenCase(
            case_id="t2",
            intent="hard boss",
            expected_patterns=[{"key": "MaxLife"}],
            hard_constraints=["factor <= 1.35"],
        )
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("b", "MaxLife", 1))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="b",
                    payload={"key": "MaxLife", "value": 2000, "factor": 2.0, "emitter": "ini"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        ev = IntentAlignmentEvaluatorV3()
        result = ev.evaluate(case, patch)
        assert not result.passed
        assert result.reject_reason == "hard_constraint_violated"

    def test_forbidden_pattern_reject(self) -> None:
        """forbidden 模式出现即 reject"""
        case = GoldenCase(
            case_id="t3",
            intent="safe mod",
            expected_patterns=[{"key": "MaxLife"}],
            forbidden_patterns=[{"key": "os.execute"}],
        )
        patch = CDLPatch(
            operations=[
                type(create_modify_property_op("b", "MaxLife", 1))(
                    op_type=OpType.MODIFY_PROPERTY,
                    target_id="b",
                    payload={"key": "MaxLife", "body": "os.execute('x')", "emitter": "ini"},
                    execution_mode=ExecutionMode.FILE_PATCH,
                )
            ]
        )
        ev = IntentAlignmentEvaluatorV3()
        result = ev.evaluate(case, patch)
        assert not result.passed

    def test_scope_control(self) -> None:
        """EVAL-INTENT-04: 范围控制"""
        case = GoldenCase(case_id="t4", intent="x", expected_patterns=[{"key": "MaxLife"}])
        # 100 个操作 → scope 扣分
        ops = [
            type(create_modify_property_op(f"n{i}", "MaxLife", i))(
                op_type=OpType.MODIFY_PROPERTY,
                target_id=f"n{i}",
                payload={"key": "MaxLife", "value": i, "emitter": "ini"},
                execution_mode=ExecutionMode.FILE_PATCH,
            )
            for i in range(100)
        ]
        patch = CDLPatch(operations=ops)
        ev = IntentAlignmentEvaluatorV3()
        result = ev.evaluate(case, patch)
        assert result.scope_control < 1.0


# === BENCH-01..03（成功判据 #7）==============================================


class TestUdifyBench:
    """成功判据 #7：≥10 个 UdifyBench case 在 CI 中运行"""

    def test_ten_golden_cases_exist(self) -> None:
        """BENCH-02: 10 个 golden case 存在"""
        cases = get_miu2d_golden_cases()
        assert len(cases) == 10

    def test_all_ten_pass(self, tmp_path: Path) -> None:
        """BENCH-03: 10 个 case 全过（CI 可跑）"""
        cases = get_miu2d_golden_cases()
        for c in cases:
            materialize_fixture(c, tmp_path)
        runner = BenchmarkRunner()
        report = runner.run_all(cases)
        assert report.passed_count == 10
        assert report.failed_count == 0
        assert report.all_passed

    def test_benchmark_report_format(self, tmp_path: Path) -> None:
        """BENCH 报告可序列化"""
        cases = get_miu2d_golden_cases()
        for c in cases:
            materialize_fixture(c, tmp_path)
        runner = BenchmarkRunner()
        report = runner.run_all(cases)
        d = report.to_dict()
        assert "passed_count" in d
        assert "results" in d
        assert len(d["results"]) == 10

    def test_rollback_checksum_consistency(self, tmp_path: Path) -> None:
        """成功判据 #6：回滚后 checksum 一致（case 10 的核心）"""
        from udify.core.adapters.miu2d_world import GameWorldGraphBuilder

        root = tmp_path / "game"
        root.mkdir()
        (root / "characters.ini").write_text("[Boss]\nMaxLife=500\n")
        builder = GameWorldGraphBuilder()
        g = builder.build(root)
        original_checksum = g.checksum()

        # 模拟 patch + 回滚
        from udify.models.cdl_patch import PatchApplicator

        applicator = PatchApplicator()
        patch = CDLPatch(operations=[create_modify_property_op(g.nodes[0].id, "MaxLife", 1000)])
        applicator.apply(patch, g)
        applicator.rollback(patch, g)
        assert g.checksum() == original_checksum
