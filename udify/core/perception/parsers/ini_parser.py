"""
Udify Perception - miu2d INI Parser

解析 miu2d 的 INI 配置文件，提取游戏对象节点。

INI 格式特点：
- 使用 Windows INI 格式 [Section]
- 键值对：Key=Value
- 支持整数、浮点数、字符串、布尔值
- 常见文件：角色属性、物品配置、地图配置
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from udify.models.content_graph import ContentGraph, ContentNode, NodeType


class INIParser:
    """
    INI 文件解析器

    将 INI 文件解析为 ContentGraph 中的节点。
    每个 [Section] 对应一个节点。
    """

    def __init__(self) -> None:
        self._type_hints: dict[str, type] = {
            "MaxLife": int,
            "MaxMana": int,
            "Strength": int,
            "Dexterity": int,
            "Intelligence": int,
            "Luck": int,
            "Level": int,
            "Exp": int,
            "Gold": int,
            "Price": int,
            "Attack": int,
            "Defense": int,
            "Speed": float,
            "CriticalRate": float,
            "DropRate": float,
        }

    def parse(self, file_path: Path, rel_path: str, graph: ContentGraph) -> list[ContentNode]:
        """
        解析 INI 文件并添加到图谱

        Returns:
            创建的节点列表
        """
        content = file_path.read_text(encoding="utf-8")
        nodes = []

        # 解析所有 Section
        sections = self._parse_sections(content)

        for section_name, properties in sections.items():
            # 推断节点类型
            node_type = self._infer_node_type(rel_path, section_name, properties)

            # 创建节点 ID
            node_id = self._generate_node_id(rel_path, section_name)

            # 类型转换
            typed_properties = self._convert_types(properties)

            node = ContentNode(
                id=node_id,
                type=node_type,
                name=section_name,
                properties=typed_properties,
                source_path=rel_path,
            )

            graph.add_node(node)
            nodes.append(node)

            # 建立文件到节点的包含关系
            file_node_id = f"file:{rel_path}"
            if not any(n.id == file_node_id for n in graph.nodes):
                file_node = ContentNode(
                    id=file_node_id,
                    type=NodeType.RESOURCE,
                    name=rel_path,
                    source_path=rel_path,
                )
                graph.add_node(file_node)

            from udify.models.content_graph import ContentEdge, EdgeType

            graph.add_edge(
                ContentEdge(
                    source=file_node_id,
                    target=node_id,
                    type=EdgeType.CONTAINS,
                )
            )

        return nodes

    def _parse_sections(self, content: str) -> dict[str, dict[str, str]]:
        """解析 INI 内容为 Section 字典"""
        sections: dict[str, dict[str, str]] = {}
        current_section = None

        for line in content.splitlines():
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith(";") or line.startswith("#"):
                continue

            # Section 头
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                sections[current_section] = {}
                continue

            # 键值对
            if current_section is not None and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                sections[current_section][key] = value

        return sections

    def _infer_node_type(
        self,
        file_path: str,
        section_name: str,
        properties: dict[str, str],
    ) -> NodeType:
        """根据上下文推断节点类型"""
        path_lower = file_path.lower()
        section_lower = section_name.lower()

        # 根据文件名推断
        if "boss" in path_lower or "boss" in section_lower:
            return NodeType.CHARACTER
        if "enemy" in path_lower or "monster" in path_lower:
            return NodeType.CHARACTER
        if "npc" in path_lower:
            return NodeType.CHARACTER
        if "player" in path_lower or "hero" in path_lower:
            return NodeType.CHARACTER
        if "item" in path_lower or "weapon" in path_lower or "armor" in path_lower:
            return NodeType.ITEM
        if "skill" in path_lower or "magic" in path_lower or "spell" in path_lower:
            return NodeType.MECHANIC
        if "map" in path_lower or "level" in path_lower or "scene" in path_lower:
            return NodeType.LEVEL
        if "quest" in path_lower or "mission" in path_lower:
            return NodeType.QUEST
        if "dialogue" in path_lower or "talk" in path_lower:
            return NodeType.DIALOGUE

        # 根据属性推断
        if "MaxLife" in properties or "MaxMana" in properties:
            return NodeType.CHARACTER
        if "Attack" in properties or "Defense" in properties:
            if "Price" in properties or "DropRate" in properties:
                return NodeType.ITEM
            return NodeType.CHARACTER
        if "Price" in properties or "Cost" in properties:
            return NodeType.ITEM
        if "ExpReward" in properties or "Exp" in properties:
            if "MaxLife" not in properties:
                return NodeType.QUEST

        return NodeType.RESOURCE

    def _generate_node_id(self, file_path: str, section_name: str) -> str:
        """生成节点 ID"""
        # 使用文件名 + Section 名
        safe_file = file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        safe_section = re.sub(r"[^a-zA-Z0-9_\-]", "_", section_name)
        return f"{safe_file}_{safe_section}"

    def _convert_types(self, properties: dict[str, str]) -> dict[str, Any]:
        """转换属性值为适当类型"""
        result = {}
        for key, value in properties.items():
            result[key] = self._convert_value(key, value)
        return result

    def _convert_value(self, key: str, value: str) -> Any:
        """转换单个值"""
        # 尝试整数
        try:
            return int(value)
        except ValueError:
            pass

        # 尝试浮点数
        try:
            return float(value)
        except ValueError:
            pass

        # 布尔值
        lower = value.lower()
        if lower in ("true", "yes", "1"):
            return True
        if lower in ("false", "no", "0"):
            return False

        # 字符串（去掉引号）
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        if value.startswith("'") and value.endswith("'"):
            return value[1:-1]

        return value

    def apply_patch_to_content(
        self,
        content: str,
        section_name: str,
        key: str,
        new_value: Any,
    ) -> str:
        """
        将修改应用到 INI 内容

        Returns:
            修改后的内容
        """
        lines = content.splitlines()
        in_target_section = False
        modified = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检查是否进入目标 Section
            if stripped.startswith("[") and stripped.endswith("]"):
                section = stripped[1:-1].strip()
                in_target_section = section == section_name
                continue

            # 在目标 Section 中查找键
            if in_target_section and "=" in line:
                current_key = line.split("=", 1)[0].strip()
                if current_key == key:
                    # 保持缩进
                    indent = line[: len(line) - len(line.lstrip())]
                    lines[i] = f"{indent}{key}={new_value}"
                    modified = True
                    break

        if not modified:
            # 如果未找到，在目标 Section 末尾添加
            # 找到 Section 的位置
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == f"[{section_name}]":
                    # 找到 Section 的结束位置
                    insert_pos = i + 1
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip().startswith("["):
                            break
                        insert_pos = j + 1

                    indent = "    "
                    lines.insert(insert_pos, f"{indent}{key}={new_value}")
                    break

        return "\n".join(lines)
