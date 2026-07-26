"""
Tree-sitter Lua 分析器（ADAPT-MIU2D-04）。

对应 MODULE-ATTACK-MAP-v3 §5 ADAPT-MIU2D-04「Tree-sitter Lua 接入：函数、调用、
危险 API；Lua AST golden test」。

替代手写 ``lua_parser`` 的脆弱正则部分。用 tree-sitter 拿到结构化 AST，提取：
- 函数定义（function_declaration）
- 函数调用（function_call）——尤其是危险 API
- 危险 API 模式（os.execute / io.popen / loadstring / dofile 等）

若 tree-sitter/tree-sitter-lua 未安装，优雅降级（返回空结果 + 标记 unavailable）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.models.content_graph import ContentEdge, ContentGraph, ContentNode, EdgeType, NodeType
from udify.models.source import Confidence, SourceSpan, ToolRunRef

# miu2d / Lua 危险 API 模式（prompt-injection / RCE 面，对应 §7.2）
DANGEROUS_APIS: dict[str, str] = {
    "os.execute": "arbitrary_command_execution",
    "os.exit": "process_termination",
    "io.popen": "arbitrary_command_execution",
    "io.open": "file_system_access",
    "loadstring": "dynamic_code_execution",
    "dofile": "dynamic_code_execution",
    "require": "module_load",
    "loadfile": "dynamic_code_execution",
    "package.loadlib": "native_library_load",
    "raw_execute": "arbitrary_command_execution",
}


@dataclass
class LuaAnalysis:
    """一次 Lua 文件分析的结果。"""

    functions: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    dangerous_calls: list[dict[str, Any]] = field(default_factory=list)
    available: bool = True
    error: str = ""


class TreeSitterLuaParser:
    """基于 tree-sitter 的 Lua 分析器。"""

    def __init__(self) -> None:
        self._parser: Any = None
        self._available = False
        try:
            import tree_sitter
            import tree_sitter_lua  # type: ignore[import-not-found]

            language = tree_sitter.Language(tree_sitter_lua.language())
            self._parser = tree_sitter.Parser(language)
            self._available = True
        except Exception:
            # 优雅降级：tree-sitter 未安装时标记不可用（不阻断主流程）
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def analyze(self, source: bytes | str) -> LuaAnalysis:
        """分析 Lua 源码，返回函数/调用/危险 API。"""
        if not self._available:
            return LuaAnalysis(available=False, error="tree-sitter-lua not installed")
        code = source.encode("utf-8") if isinstance(source, str) else source
        try:
            tree = self._parser.parse(code)
        except Exception as e:
            return LuaAnalysis(available=False, error=str(e))

        analysis = LuaAnalysis()
        self._walk(tree.root_node, code, analysis)
        return analysis

    def parse(self, file_path: Path, rel_path: str, graph: ContentGraph) -> list[ContentNode]:
        """解析 Lua 文件并写入 ContentGraph（输出带 SourceSpan 的节点）。"""
        try:
            code = file_path.read_bytes()
        except Exception:
            return []

        analysis = self.analyze(code)
        extractor = ToolRunRef(tool_id="lua_ts_parser", version="1.0")
        added: list[ContentNode] = []

        # 文件节点
        file_node_id = f"lua:{rel_path}"
        file_node = ContentNode(
            id=file_node_id,
            type=NodeType.RESOURCE,
            name=file_path.name,
            properties={"lang": "lua", "engine": "miu2d"},
            source_path=rel_path,
            source_span=SourceSpan(file_path=rel_path, extractor=extractor),
            confidence=Confidence(score=1.0, method="parser"),
            semantic_tags=["script"],
        )
        graph.add_node(file_node)
        added.append(file_node)

        if not analysis.available:
            file_node.properties["parse_error"] = analysis.error
            return added

        # 函数 → MECHANIC 节点
        for func in analysis.functions:
            func_id = f"{file_node_id}:fn:{func['name']}:{func['start_line']}"
            node = ContentNode(
                id=func_id,
                type=NodeType.MECHANIC,
                name=func["name"],
                properties={
                    "kind": "function",
                    "params": func.get("params", []),
                    "start_line": func["start_line"],
                    "end_line": func["end_line"],
                },
                source_path=rel_path,
                source_span=SourceSpan(
                    file_path=rel_path,
                    line_start=func["start_line"],
                    line_end=func["end_line"],
                    extractor=extractor,
                    ast_path=("function", func["name"]),
                ),
                confidence=Confidence(score=0.95, method="parser"),
                semantic_tags=["lua_function"],
            )
            graph.add_node(node)
            graph.add_edge(ContentEdge(source=file_node_id, target=func_id, type=EdgeType.CONTAINS))
            added.append(node)

        # 危险 API 调用 → EVENT 节点（带 danger 标签）
        for call in analysis.dangerous_calls:
            call_id = f"{file_node_id}:call:{call['name']}:{call['line']}"
            node = ContentNode(
                id=call_id,
                type=NodeType.EVENT,
                name=call["name"],
                properties={
                    "kind": "dangerous_call",
                    "danger_category": call["category"],
                    "line": call["line"],
                    "raw": call.get("raw", ""),
                },
                source_path=rel_path,
                source_span=SourceSpan(
                    file_path=rel_path,
                    line_start=call["line"],
                    line_end=call["line"],
                    extractor=extractor,
                    ast_path=("call", call["name"]),
                ),
                confidence=Confidence(score=1.0, method="parser"),
                semantic_tags=["dangerous_api", call["category"]],
            )
            graph.add_node(node)
            graph.add_edge(ContentEdge(source=file_node_id, target=call_id, type=EdgeType.CONTAINS))
            added.append(node)

        return added

    def _walk(self, node: Any, code: bytes, analysis: LuaAnalysis, level: int = 0) -> None:
        """递归遍历 AST。"""
        if level > 50:  # 深度保护
            return

        t = node.type

        if t == "function_declaration":
            name = self._extract_function_name(node, code)
            params = self._extract_params(node, code)
            analysis.functions.append(
                {
                    "name": name,
                    "params": params,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                }
            )

        elif t == "function_call":
            call_name = self._extract_call_name(node, code)
            if call_name:
                line = node.start_point[0] + 1
                raw = code[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
                analysis.calls.append({"name": call_name, "line": line, "raw": raw})
                # 检查危险 API
                danger = self._check_dangerous(call_name)
                if danger:
                    analysis.dangerous_calls.append(
                        {
                            "name": call_name,
                            "line": line,
                            "category": danger,
                            "raw": raw,
                        }
                    )

        for child in node.children:
            self._walk(child, code, analysis, level + 1)

    def _extract_function_name(self, node: Any, code: bytes) -> str:
        """从 function_declaration 节点提取函数名。"""
        for child in node.children:
            if child.type in (
                "identifier",
                "function_name",
                "method_index_expression",
                "field_expression",
            ):
                return code[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
            if child.type == "function_name_field":
                return code[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
        return "<anonymous>"

    def _extract_params(self, node: Any, code: bytes) -> list[str]:
        """提取参数列表。"""
        for child in node.children:
            if child.type == "parameters":
                return [
                    code[c.start_byte : c.end_byte].decode("utf-8", errors="replace")
                    for c in child.children
                    if c.type == "identifier"
                ]
        return []

    def _extract_call_name(self, node: Any, code: bytes) -> str:
        """从 function_call 节点提取被调名称。"""
        for child in node.children:
            if child.type in (
                "identifier",
                "field_expression",
                "method_index_expression",
                "dot_index_expression",
            ):
                return code[child.start_byte : child.end_byte].decode("utf-8", errors="replace")
        return ""

    def _check_dangerous(self, call_name: str) -> str | None:
        """检查调用名是否匹配危险 API（大小写/点/空格不敏感）。"""
        from udify.core.text_normalize import normalize_identifier

        name = normalize_identifier(call_name)
        for api, category in DANGEROUS_APIS.items():
            api_norm = normalize_identifier(api)
            if api_norm and api_norm in name:
                return category
        return None


__all__ = ["DANGEROUS_APIS", "LuaAnalysis", "TreeSitterLuaParser"]
