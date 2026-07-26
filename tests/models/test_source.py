"""
证据链原语测试（DATA-CG-01..05, DATA-CG-08）。

覆盖：
- SourceSpan / Provenance / Confidence / Evidence / ToolRunRef 的 round-trip
- Confidence 分数截断到 [0,1]
- ContentNode v3 optional 字段向后兼容
- graph checksum 稳定 + 回滚一致性（成功判据 #6）
- PatchOperation execution_mode / risk / source_span

对应 ITERATION-PLAN-2026-07.md §4.1。
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from udify.models.cdl_patch import (
    CDLPatch,
    ExecutionMode,
    OpType,
    PatchApplicator,
    PatchOperation,
    create_modify_property_op,
)
from udify.models.content_graph import ContentEdge, ContentGraph, ContentNode, EdgeType, NodeType
from udify.models.source import Confidence, Evidence, Provenance, SourceSpan, ToolRunRef


class TestSourcePrimitivesRoundTrip:
    """证据链原语 round-trip"""

    def test_tool_run_ref_roundtrip(self) -> None:
        ref = ToolRunRef(tool_id="ini_parser", version="1.0", args_hash="abc", input_hash="def")
        rt = ToolRunRef.from_dict(ref.to_dict())
        assert rt == ref

    def test_source_span_roundtrip(self) -> None:
        span = SourceSpan(
            file_path="characters.ini",
            line_start=1,
            line_end=3,
            ast_path=("Boss", "MaxLife"),
            content_hash="deadbeef",
            extractor=ToolRunRef(tool_id="ini_parser"),
        )
        rt = SourceSpan.from_dict(span.to_dict())
        assert rt.file_path == span.file_path
        assert rt.ast_path == span.ast_path
        assert rt.extractor is not None
        assert rt.extractor.tool_id == "ini_parser"

    def test_provenance_roundtrip(self) -> None:
        prov = Provenance(tool=ToolRunRef(tool_id="x"), method="ini_section_parse")
        rt = Provenance.from_dict(prov.to_dict())
        assert rt.method == "ini_section_parse"

    def test_evidence_roundtrip(self) -> None:
        ev = Evidence(
            evidence_id="e1",
            description="boss hp found",
            span=SourceSpan(file_path="a.ini"),
            payload={"raw": "MaxLife=500"},
        )
        rt = Evidence.from_dict(ev.to_dict())
        assert rt.evidence_id == "e1"
        assert rt.span is not None


class TestConfidence:
    """置信度分数截断"""

    @given(score=st.floats(min_value=-10, max_value=10, allow_nan=False))
    def test_score_clamped_to_unit_interval(self, score: float) -> None:
        c = Confidence(score=score)
        assert 0.0 <= c.score <= 1.0

    def test_unknown_method_default(self) -> None:
        c = Confidence()
        assert c.method == "unknown"
        assert c.score == 0.0


class TestContentNodeV3Fields:
    """ContentNode v3 optional 字段向后兼容"""

    def test_old_construction_still_works(self) -> None:
        """旧代码不传 v3 字段也能构造"""
        node = ContentNode(id="n1", type=NodeType.CHARACTER, name="Boss")
        assert node.semantic_tags == []
        assert node.provenance is None
        assert node.confidence is None
        assert node.license_hint == "unknown"

    def test_to_dict_omits_empty_v3_fields(self) -> None:
        """空 v3 字段不出现在 to_dict（旧格式兼容）"""
        node = ContentNode(id="n1", type=NodeType.RESOURCE, name="x")
        d = node.to_dict()
        assert "semantic_tags" not in d
        assert "provenance" not in d
        assert "license_hint" not in d

    def test_to_dict_includes_set_v3_fields(self) -> None:
        node = ContentNode(
            id="n1",
            type=NodeType.CHARACTER,
            name="Boss",
            semantic_tags=["enemy"],
            confidence=Confidence(score=0.9, method="parser"),
            license_hint="proprietary",
        )
        d = node.to_dict()
        assert d["semantic_tags"] == ["enemy"]
        assert d["confidence"]["score"] == 0.9
        assert d["license_hint"] == "proprietary"


class TestGraphChecksum:
    """graph checksum（DATA-CG-08）—— 成功判据 #6 回滚一致性"""

    def _sample_graph(self) -> ContentGraph:
        g = ContentGraph()
        g.add_node(
            ContentNode(id="boss", type=NodeType.CHARACTER, name="Boss", properties={"hp": 500})
        )
        g.add_node(
            ContentNode(id="hero", type=NodeType.CHARACTER, name="Hero", properties={"hp": 100})
        )
        g.add_edge(ContentEdge(source="boss", target="hero", type=EdgeType.DEPENDS_ON))
        return g

    def test_checksum_stable(self) -> None:
        """相同结构 → 相同 checksum"""
        assert self._sample_graph().checksum() == self._sample_graph().checksum()

    def test_checksum_order_independent(self) -> None:
        """节点顺序不同但内容相同 → 相同 checksum"""
        g1 = ContentGraph()
        g1.add_node(ContentNode(id="a", type=NodeType.RESOURCE, name="A"))
        g1.add_node(ContentNode(id="b", type=NodeType.RESOURCE, name="B"))
        g2 = ContentGraph()
        g2.add_node(ContentNode(id="b", type=NodeType.RESOURCE, name="B"))
        g2.add_node(ContentNode(id="a", type=NodeType.RESOURCE, name="A"))
        assert g1.checksum() == g2.checksum()

    def test_checksum_changes_on_mutation(self) -> None:
        g = self._sample_graph()
        before = g.checksum()
        g.nodes[0].properties["hp"] = 999
        assert g.checksum() != before

    def test_rollback_restores_checksum(self) -> None:
        """patch 应用后再回滚，checksum 应回到原始（成功判据 #6）"""
        g = self._sample_graph()
        original = g.checksum()

        patch = CDLPatch(
            operations=[create_modify_property_op("boss", "hp", 999)],
            intent="test",
        )
        applicator = PatchApplicator()
        ok, _ = applicator.apply(patch, g)
        assert ok
        assert g.checksum() != original  # 应用后变了

        applicator.rollback(patch, g)
        assert g.checksum() == original  # 回滚后一致


class TestPatchOperationV3Fields:
    """PatchOperation v3 字段（DATA-PATCH-01..06）"""

    def test_default_execution_mode_graph_only(self) -> None:
        op = create_modify_property_op("n1", "hp", 100)
        assert op.execution_mode == ExecutionMode.GRAPH_ONLY

    def test_file_patch_mode(self) -> None:
        op = PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id="n1",
            payload={"key": "hp", "value": 100},
            execution_mode=ExecutionMode.FILE_PATCH,
            planning_reason="double hp",
            risk=0.3,
        )
        assert op.execution_mode == ExecutionMode.FILE_PATCH
        assert op.planning_reason == "double hp"
        assert op.risk == 0.3

    def test_execution_mode_values(self) -> None:
        assert {m.value for m in ExecutionMode} == {
            "graph_only",
            "file_patch",
            "runtime_hook",
            "package_overlay",
        }
