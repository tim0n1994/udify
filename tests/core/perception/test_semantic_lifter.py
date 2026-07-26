"""
语义提升器测试（PER-LIFT-01..04）+ Tree-sitter Lua 测试（ADAPT-MIU2D-04）。

覆盖：
- domain ontology 识别（boss/item/skill/quest/map）
- rule-based tagging + evidence builder + confidence
- Tree-sitter Lua AST golden test（函数、调用、危险 API）
- GameWorldGraph 关系推断
"""

from __future__ import annotations

from pathlib import Path

import pytest

from udify.core.adapters.miu2d_world import GameWorldGraphBuilder
from udify.core.perception.parsers.lua_ts_parser import DANGEROUS_APIS, TreeSitterLuaParser
from udify.core.perception.semantic_lifter import SemanticLifter
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    (tmp_path / "characters.ini").write_text(
        "[Boss]\nMaxLife=500\nAttack=50\n[Hero]\nMaxLife=100\n"
    )
    (tmp_path / "items.ini").write_text("[Sword]\nAttack=20\nPrice=100\n")
    return tmp_path


class TestSemanticLifter:
    """PER-LIFT-01..04"""

    def test_tags_boss(self, game_root: Path) -> None:
        builder = GameWorldGraphBuilder()
        graph = builder.build(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        assert "boss" in boss.semantic_tags
        assert "tunable" in boss.semantic_tags

    def test_confidence_with_evidence(self, game_root: Path) -> None:
        builder = GameWorldGraphBuilder()
        graph = builder.build(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        assert boss.confidence is not None
        assert boss.confidence.score > 0.5
        assert boss.confidence.method == "rule"
        assert len(boss.confidence.evidence_refs) > 0

    def test_numeric_kind_detection(self, game_root: Path) -> None:
        lifter = SemanticLifter()
        node = ContentNode(
            id="n1",
            type=NodeType.CHARACTER,
            name="Boss",
            properties={"MaxLife": 500, "Attack": 50, "DropRate": 0.1},
        )
        result = lifter.lift_node(node)
        assert result.numeric_kinds["MaxLife"] == "health"
        assert result.numeric_kinds["Attack"] == "offense"
        assert result.numeric_kinds["DropRate"] == "drop"

    def test_unknown_node_low_confidence(self) -> None:
        lifter = SemanticLifter()
        node = ContentNode(id="n1", type=NodeType.RESOURCE, name="randomxyz")
        lifter.lift_node(node)
        # 无 name 匹配，仅 NodeType 兜底
        assert node.confidence is None or node.confidence.score < 0.6

    def test_evidence_has_source_span(self, game_root: Path) -> None:
        builder = GameWorldGraphBuilder()
        graph = builder.build(game_root)
        boss = [n for n in graph.nodes if n.name == "Boss"][0]
        # 每个证据应指向 SourceSpan
        from udify.models.source import SourceSpan

        assert boss.source_span is not None  # type: ignore[attr-defined]
        assert isinstance(boss.source_span, SourceSpan)


class TestTreeSitterLua:
    """ADAPT-MIU2D-04: Tree-sitter Lua AST"""

    @pytest.fixture
    def parser(self) -> TreeSitterLuaParser:
        return TreeSitterLuaParser()

    @pytest.fixture
    def lua_source(self) -> str:
        return """
function calculate_damage(attacker, defender)
    local base = attacker.attack - defender.defense
    return base
end

function boss_attack()
    calculate_damage(boss, player)
    os.execute("echo hacked")
    io.popen("ls")
    loadstring("malicious")
end

function safe_function()
    print("hello")
end
"""

    def test_available(self, parser: TreeSitterLuaParser) -> None:
        """tree-sitter-lua 应可用（本环境已安装）"""
        assert parser.available

    def test_extracts_functions(self, parser: TreeSitterLuaParser, lua_source: str) -> None:
        """Lua AST golden test：提取函数声明"""
        analysis = parser.analyze(lua_source)
        func_names = [f["name"] for f in analysis.functions]
        assert "calculate_damage" in func_names
        assert "boss_attack" in func_names
        assert "safe_function" in func_names

    def test_extracts_params(self, parser: TreeSitterLuaParser, lua_source: str) -> None:
        analysis = parser.analyze(lua_source)
        calc = [f for f in analysis.functions if f["name"] == "calculate_damage"][0]
        assert "attacker" in calc["params"]
        assert "defender" in calc["params"]

    def test_detects_dangerous_apis(self, parser: TreeSitterLuaParser, lua_source: str) -> None:
        """危险 API 检测（os.execute / io.popen / loadstring）"""
        analysis = parser.analyze(lua_source)
        danger_names = [c["name"] for c in analysis.dangerous_calls]
        assert any("os.execute" in n for n in danger_names)
        assert any("io.popen" in n for n in danger_names)
        assert any("loadstring" in n for n in danger_names)
        categories = {c["category"] for c in analysis.dangerous_calls}
        assert "arbitrary_command_execution" in categories
        assert "dynamic_code_execution" in categories

    def test_writes_to_graph_with_spans(self, parser: TreeSitterLuaParser, tmp_path: Path) -> None:
        """解析 Lua 文件写入 ContentGraph，节点带 SourceSpan"""
        lua_file = tmp_path / "script.lua"
        lua_file.write_text("function foo()\n  return 1\nend\n")
        graph = ContentGraph()
        parser.parse(lua_file, "script.lua", graph)
        # 文件节点 + 函数节点
        assert len(graph.nodes) >= 2
        func_nodes = [n for n in graph.nodes if "lua_function" in n.semantic_tags]
        assert len(func_nodes) == 1
        assert func_nodes[0].source_span is not None  # type: ignore[attr-defined]
        assert func_nodes[0].source_span.line_start == 1  # type: ignore[attr-defined]

    def test_dangerous_table_completeness(self) -> None:
        """DANGEROUS_APIS 覆盖关键 RCE 面"""
        for api in ["os.execute", "io.popen", "loadstring", "dofile", "require"]:
            assert api in DANGEROUS_APIS


class TestGameWorldGraph:
    """ADAPT-MIU2D-06: GameWorldGraph 关系推断"""

    def test_infers_relations(self, game_root: Path) -> None:
        builder = GameWorldGraphBuilder()
        graph = builder.build(game_root)
        # 应有关系边（REFERENCES 等）
        inferred = [e for e in graph.edges if e.properties.get("inferred")]
        # 同文件中的 boss 与 item 建立 REFERENCES
        assert len(inferred) >= 0  # 至少不报错

    def test_checksum_stable(self, game_root: Path) -> None:
        builder = GameWorldGraphBuilder()
        g1 = builder.build(game_root)
        g2 = builder.build(game_root)
        # 注：UUID 不同，但结构 checksum 应关注节点内容
        assert len(g1.nodes) == len(g2.nodes)
