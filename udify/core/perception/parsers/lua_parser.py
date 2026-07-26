"""
Udify Perception - Lua Script Parser

解析 Lua 脚本，提取游戏逻辑相关的函数和变量。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from udify.models.content_graph import ContentEdge, ContentGraph, ContentNode, EdgeType, NodeType


class LuaParser:
    """
    Lua 脚本解析器

    基于正则和启发式的 Lua 解析（非完整 AST）。
    提取：
    - 函数定义
    - 全局变量（配置值）
    - 事件回调
    - 游戏 API 调用
    """

    # 常见的游戏相关 API 模式
    GAME_APIS = {
        r"GetPlayer\s*\(": "player_access",
        r"SetPlayerProperty\s*\(": "player_modify",
        r"GetEnemy\s*\(": "enemy_access",
        r"SetEnemyProperty\s*\(": "enemy_modify",
        r"AddItem\s*\(": "item_give",
        r"RemoveItem\s*\(": "item_take",
        r"Spawn\s*\(": "spawn",
        r"Teleport\s*\(": "teleport",
        r"PlaySound\s*\(": "sound",
        r"PlayMusic\s*\(": "music",
        r"ShowMessage\s*\(": "ui_message",
        r"OpenShop\s*\(": "shop",
        r"SetFlag\s*\(": "flag",
        r"GetFlag\s*\(": "flag",
        r"SaveGame\s*\(": "save",
        r"LoadGame\s*\(": "load",
    }

    def parse(self, file_path: Path, rel_path: str, graph: ContentGraph) -> list[ContentNode]:
        """解析 Lua 脚本并添加到图谱"""
        content = file_path.read_text(encoding="utf-8")
        nodes = []

        # 提取函数
        functions = self._extract_functions(content)
        for func_name, func_data in functions.items():
            node_id = self._generate_node_id(rel_path, func_name)

            node = ContentNode(
                id=node_id,
                type=NodeType.MECHANIC,
                name=func_name,
                properties={
                    "script_type": "lua_function",
                    "parameters": func_data.get("params", []),
                    "line_count": func_data.get("line_count", 0),
                    "calls": func_data.get("calls", []),
                    "modifies": func_data.get("modifies", []),
                    "reads": func_data.get("reads", []),
                },
                source_path=rel_path,
            )

            graph.add_node(node)
            nodes.append(node)

        # 提取全局配置变量
        globals_vars = self._extract_globals(content)
        for var_name, var_value in globals_vars.items():
            node_id = self._generate_node_id(rel_path, f"var_{var_name}")

            node = ContentNode(
                id=node_id,
                type=NodeType.RESOURCE,
                name=var_name,
                properties={
                    "script_type": "lua_global",
                    "value": var_value,
                },
                source_path=rel_path,
            )

            graph.add_node(node)
            nodes.append(node)

        # 添加文件节点
        self._add_file_node(rel_path, nodes, graph)

        return nodes

    def _extract_functions(self, content: str) -> dict[str, dict[str, Any]]:
        """提取 Lua 函数定义"""
        functions: dict[str, dict[str, Any]] = {}

        # 模式 1: function Name(...)
        pattern1 = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)")
        for match in pattern1.finditer(content):
            func_name = match.group(1)
            params = [p.strip() for p in match.group(2).split(",") if p.strip()]
            functions[func_name] = {
                "params": params,
                "line_count": 0,
                "calls": [],
                "modifies": [],
                "reads": [],
            }

        # 模式 2: Name = function(...)
        pattern2 = re.compile(r"(\w+)\s*=\s*function\s*\(([^)]*)\)")
        for match in pattern2.finditer(content):
            func_name = match.group(1)
            params = [p.strip() for p in match.group(2).split(",") if p.strip()]
            if func_name not in functions:
                functions[func_name] = {
                    "params": params,
                    "line_count": 0,
                    "calls": [],
                    "modifies": [],
                    "reads": [],
                }

        # 分析每个函数的内容
        for func_name in functions:
            func_content = self._extract_function_content(content, func_name)
            if func_content:
                functions[func_name]["line_count"] = len(func_content.splitlines())
                functions[func_name]["calls"] = self._extract_calls(func_content)
                functions[func_name]["modifies"] = self._extract_modifications(func_content)
                functions[func_name]["reads"] = self._extract_reads(func_content)

        return functions

    def _extract_function_content(self, content: str, func_name: str) -> str:
        """提取函数体内容（简化版）"""
        # 找到函数开始
        start_match = re.search(
            rf"(?:function\s+{func_name}|{func_name}\s*=\s*function)\s*\([^)]*\)",
            content,
        )
        if not start_match:
            return ""

        start_pos = start_match.end()

        # 找到匹配的 end（简化：数 function/end 对）
        depth = 1
        pos = start_pos
        while depth > 0 and pos < len(content):
            # 找下一个 function 或 end
            next_func = content.find("function", pos)
            next_end = content.find("end", pos)

            if next_end == -1:
                break

            if next_func != -1 and next_func < next_end:
                depth += 1
                pos = next_func + 8
            else:
                depth -= 1
                pos = next_end + 3

        return content[start_pos:pos]

    def _extract_calls(self, content: str) -> list[str]:
        """提取函数调用"""
        calls = []
        pattern = re.compile(r"(\w+)\s*\(")
        for match in pattern.finditer(content):
            call_name = match.group(1)
            if call_name not in ["if", "while", "for", "return", "local", "function"]:
                calls.append(call_name)
        return list(set(calls))

    def _extract_modifications(self, content: str) -> list[str]:
        """提取修改操作"""
        modifies = []

        # 检查游戏 API 修改调用
        for pattern, api_type in self.GAME_APIS.items():
            if re.search(pattern, content, re.IGNORECASE):
                modifies.append(api_type)

        # 检查变量赋值
        for match in re.finditer(r"(\w+)\s*=\s*([^=].*?)(?:\n|$)", content):
            var_name = match.group(1).strip()
            if var_name not in ["if", "for", "while", "return", "local"]:
                modifies.append(f"set_{var_name}")

        return list(set(modifies))

    def _extract_reads(self, content: str) -> list[str]:
        """提取读取操作"""
        reads = []

        # 检查全局变量读取
        for match in re.finditer(r"[^\w.](\w+)(?:\s*\[.*?\])?\s*[^=]", content):
            var_name = match.group(1)
            if var_name not in [
                "if",
                "for",
                "while",
                "return",
                "local",
                "function",
                "end",
                "then",
                "do",
            ]:
                reads.append(var_name)

        return list(set(reads))

    def _extract_globals(self, content: str) -> dict[str, Any]:
        """提取全局配置变量"""
        globals_vars: dict[str, Any] = {}

        # 模式: VAR_NAME = value
        for match in re.finditer(r"^(\w+)\s*=\s*(.+)$", content, re.MULTILINE):
            var_name = match.group(1)
            value_str = match.group(2).strip()

            # 跳过函数定义
            if "function" in value_str:
                continue

            # 尝试转换值
            globals_vars[var_name] = self._convert_value(value_str)

        return globals_vars

    def _convert_value(self, value_str: str) -> Any:
        """转换 Lua 值"""
        value_str = value_str.strip()

        # 整数
        try:
            return int(value_str)
        except ValueError:
            pass

        # 浮点数
        try:
            return float(value_str)
        except ValueError:
            pass

        # 布尔值
        if value_str.lower() == "true":
            return True
        if value_str.lower() == "false":
            return False

        # 字符串
        if (value_str.startswith('"') and value_str.endswith('"')) or (
            value_str.startswith("'") and value_str.endswith("'")
        ):
            return value_str[1:-1]

        # 表（简化处理）
        if value_str.startswith("{") and value_str.endswith("}"):
            return {"_raw": value_str, "_type": "table"}

        return value_str

    def _add_file_node(self, rel_path: str, nodes: list[ContentNode], graph: ContentGraph) -> None:
        """添加文件节点"""
        file_node_id = f"file:{rel_path}"
        if not any(n.id == file_node_id for n in graph.nodes):
            file_node = ContentNode(
                id=file_node_id,
                type=NodeType.RESOURCE,
                name=rel_path,
                source_path=rel_path,
            )
            graph.add_node(file_node)

            for node in nodes:
                graph.add_edge(
                    ContentEdge(
                        source=file_node_id,
                        target=node.id,
                        type=EdgeType.CONTAINS,
                    )
                )

    def _generate_node_id(self, file_path: str, name: str) -> str:
        """生成节点 ID"""
        safe_file = file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
        return f"{safe_file}_{safe_name}"
