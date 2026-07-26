"""
Udify Perception - miu2d OBJ Parser

解析 miu2d 的 OBJ 对象定义文件。

OBJ 格式特点（基于 miu2d 分析）：
- 每个对象由多行属性定义
- 常见对象类型：角色、敌人、物品、技能
- 属性比 INI 更复杂，可能包含列表和嵌套结构
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from udify.models.content_graph import ContentEdge, ContentGraph, ContentNode, EdgeType, NodeType


class OBJParser:
    """
    OBJ 文件解析器

    解析 miu2d OBJ 格式，提取结构化对象。
    """

    def __init__(self) -> None:
        self._object_types = {
            "character": NodeType.CHARACTER,
            "enemy": NodeType.CHARACTER,
            "boss": NodeType.CHARACTER,
            "npc": NodeType.CHARACTER,
            "item": NodeType.ITEM,
            "weapon": NodeType.ITEM,
            "armor": NodeType.ITEM,
            "skill": NodeType.MECHANIC,
            "magic": NodeType.MECHANIC,
            "spell": NodeType.MECHANIC,
            "map": NodeType.LEVEL,
            "level": NodeType.LEVEL,
            "scene": NodeType.LEVEL,
        }

    def parse(self, file_path: Path, rel_path: str, graph: ContentGraph) -> list[ContentNode]:
        """解析 OBJ 文件并添加到图谱"""
        content = file_path.read_text(encoding="utf-8")
        nodes = []

        objects = self._parse_objects(content)

        for obj_name, obj_data in objects.items():
            node_type = self._infer_node_type(obj_data)
            node_id = self._generate_node_id(rel_path, obj_name)

            # 提取属性
            properties = self._extract_properties(obj_data)

            node = ContentNode(
                id=node_id,
                type=node_type,
                name=obj_name,
                properties=properties,
                source_path=rel_path,
            )

            graph.add_node(node)
            nodes.append(node)

            # 处理关系
            self._extract_relationships(node, obj_data, graph)

        # 添加文件节点
        self._add_file_node(rel_path, nodes, graph)

        return nodes

    def _parse_objects(self, content: str) -> dict[str, list[str]]:
        """解析 OBJ 文件中的对象定义"""
        objects: dict[str, list[str]] = {}
        current_object: str | None = None

        for line in content.splitlines():
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue

            # 对象开始标记（多种可能格式）
            obj_match = re.match(
                r"^(?:Object|Define|Entry|@)\s+([\w_\-]+)", stripped, re.IGNORECASE
            )
            if obj_match:
                current_object = obj_match.group(1)
                objects[current_object] = []
                continue

            # 大写名称作为对象标记（全大写）
            if stripped.isupper() and len(stripped) > 1 and "=" not in stripped:
                current_object = stripped
                objects[current_object] = []
                continue

            # PascalCase/CamelCase 名称作为对象标记（首字母大写，不含 =，不是缩进行）
            if (
                (not line.startswith(" ") and not line.startswith("\t"))
                and "=" not in stripped
                and re.match(r"^[A-Z][a-zA-Z0-9_]*$", stripped)
            ):
                current_object = stripped
                objects[current_object] = []
                continue

            if current_object is not None:
                objects[current_object].append(line)

        return objects

    def _infer_node_type(self, obj_data: list[str]) -> NodeType:
        """根据对象数据推断节点类型"""
        content = "\n".join(obj_data).lower()

        for type_name, node_type in self._object_types.items():
            if type_name in content:
                return node_type

        # 根据属性推断
        if any(k in content for k in ["hp", "maxlife", "strength", "attack", "defense"]):
            return NodeType.CHARACTER
        if any(k in content for k in ["price", "cost", "durability", "equip"]):
            return NodeType.ITEM
        if any(k in content for k in ["mpcost", "cooldown", "range", "damage", "heal"]):
            return NodeType.MECHANIC
        if any(k in content for k in ["width", "height", "tile", "grid"]):
            return NodeType.LEVEL

        return NodeType.RESOURCE

    def _extract_properties(self, obj_data: list[str]) -> dict[str, Any]:
        """提取对象属性"""
        properties = {}

        for line in obj_data:
            stripped = line.strip()
            if "=" in stripped:
                key, value = stripped.split("=", 1)
                key = key.strip()
                value = value.strip()

                # 尝试类型转换
                properties[key] = self._convert_value(value)

        return properties

    def _extract_relationships(
        self, node: ContentNode, obj_data: list[str], graph: ContentGraph
    ) -> None:
        """提取对象间关系"""
        content = "\n".join(obj_data).lower()

        # 检查依赖关系
        dependency_patterns = [
            (r"require[s]?\s+([\w_\-]+)", EdgeType.REQUIRES),
            (r"depend[s]?\s+on\s+([\w_\-]+)", EdgeType.DEPENDS_ON),
            (r"trigger[s]?\s+([\w_\-]+)", EdgeType.TRIGGERS),
            (r"reference[s]?\s+([\w_\-]+)", EdgeType.REFERENCES),
        ]

        for pattern, edge_type in dependency_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                target_name = match.group(1)
                # 尝试找到目标节点
                target_id = None
                for n in graph.nodes:
                    if n.name.lower() == target_name.lower():
                        target_id = n.id
                        break

                if target_id:
                    graph.add_edge(
                        ContentEdge(
                            source=node.id,
                            target=target_id,
                            type=edge_type,
                        )
                    )

    def _generate_node_id(self, file_path: str, obj_name: str) -> str:
        """生成节点 ID"""
        safe_file = file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", obj_name)
        return f"{safe_file}_{safe_name}"

    def _add_file_node(self, rel_path: str, nodes: list[ContentNode], graph: ContentGraph) -> None:
        """添加文件节点并建立包含关系"""
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

    def _convert_value(self, value: str) -> Any:
        """转换属性值类型"""
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
        if lower in ("true", "yes"):
            return True
        if lower in ("false", "no"):
            return False

        # 列表（逗号分隔）
        if "," in value and not (value.startswith('"') or value.startswith("'")):
            items = [v.strip() for v in value.split(",")]
            # 尝试将列表项转换为数字
            converted = []
            for item in items:
                try:
                    converted.append(int(item))
                except ValueError:
                    try:
                        converted.append(float(item))
                    except ValueError:
                        converted.append(item)
            return converted

        # 去掉引号的字符串
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]

        return value
