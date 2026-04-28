"""
Udify Perception - miu2d NPC Script Parser

解析 miu2d 的 NPC 脚本（.npc / .txt 格式）。

NPC 脚本特点：
- 基于 DSL（领域特定语言）
- 命令式：Say, Move, AddLife, If, RunScript 等
- 控制流：If/Else/EndIf, Loop/EndLoop
- 事件触发：OnTalk, OnAttack, OnDeath
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from udify.models.content_graph import ContentEdge, ContentGraph, ContentNode, EdgeType, NodeType


class NPCScriptParser:
    """
    NPC 脚本解析器

    解析 .npc 和 .txt 脚本文件，提取：
    - NPC 行为节点
    - 对话节点
    - 事件触发器
    - 脚本依赖关系
    """

    # miu2d DSL 命令（基于研究文档中的 218 个命令）
    DSL_COMMANDS = {
        "say", "move", "addlife", "addmana", "setlife", "setmana",
        "if", "else", "endif", "loop", "endloop", "break",
        "runscript", "runparallelscript", "transport", "summon",
        "giveitem", "takeitem", "openshop", "closeshop",
        "setflag", "getflag", "addexp", "levelup",
        "playanimation", "playsound", "playmusic", "stopmusic",
        "wait", "delay", "random", "goto", "label",
        "spawnenemy", "removeenemy", "setenemyproperty",
        "opendoor", "closedoor", "shakecamera",
        "showmessage", "hidemessage", "choicedialog",
        "savegame", "loadgame", "gameover",
        "setplayerproperty", "getplayerproperty",
        "addmoney", "takemoney", "setmoney",
        "teleport", "warp", "changescreen",
        "enablecontrol", "disablecontrol",
        "showui", "hideui", "fadein", "fadeout",
        "setweather", "settime", "setlighting",
    }

    def __init__(self) -> None:
        self._event_handlers = {
            "ontalk": "对话触发",
            "onattack": "攻击触发",
            "ondeath": "死亡触发",
            "onspawn": "生成触发",
            "oninteract": "交互触发",
            "onenter": "进入触发",
            "onleave": "离开触发",
            "onuse": "使用触发",
            "ontimer": "定时触发",
        }

    def parse(self, file_path: Path, rel_path: str, graph: ContentGraph) -> List[ContentNode]:
        """解析 NPC 脚本并添加到图谱"""
        content = file_path.read_text(encoding="utf-8")
        nodes = []

        # 解析脚本结构
        script_blocks = self._parse_script_blocks(content)

        for block_name, block_data in script_blocks.items():
            # 创建脚本块节点
            node_id = self._generate_node_id(rel_path, block_name)

            # 提取脚本元数据
            properties = {
                "script_type": block_data.get("type", "unknown"),
                "line_count": len(block_data.get("commands", [])),
                "commands": block_data.get("commands", []),
                "events": block_data.get("events", []),
                "has_dialogue": block_data.get("has_dialogue", False),
                "has_combat": block_data.get("has_combat", False),
                "has_shop": block_data.get("has_shop", False),
            }

            node = ContentNode(
                id=node_id,
                type=NodeType.DIALOGUE if properties["has_dialogue"] else NodeType.EVENT,
                name=block_name,
                properties=properties,
                source_path=rel_path,
            )

            graph.add_node(node)
            nodes.append(node)

            # 提取对话内容作为子节点
            if properties["has_dialogue"]:
                dialogues = self._extract_dialogues(block_data.get("commands", []))
                for i, dialogue_text in enumerate(dialogues):
                    dialogue_node = ContentNode(
                        id=f"{node_id}_dialogue_{i}",
                        type=NodeType.DIALOGUE,
                        name=f"{block_name}_对话_{i}",
                        properties={"text": dialogue_text},
                        source_path=rel_path,
                    )
                    graph.add_node(dialogue_node)
                    graph.add_edge(ContentEdge(
                        source=node_id,
                        target=dialogue_node.id,
                        type=EdgeType.CONTAINS,
                    ))

        # 提取全局依赖
        self._extract_global_dependencies(content, rel_path, nodes, graph)

        # 添加文件节点
        self._add_file_node(rel_path, nodes, graph)

        return nodes

    def _parse_script_blocks(self, content: str) -> Dict[str, Dict[str, Any]]:
        """解析脚本块"""
        blocks: Dict[str, Dict[str, Any]] = {}
        current_block = "main"
        blocks[current_block] = {
            "type": "main",
            "commands": [],
            "events": [],
            "has_dialogue": False,
            "has_combat": False,
            "has_shop": False,
        }

        for line in content.splitlines():
            stripped = line.strip()

            # 跳过空行和注释
            if not stripped or stripped.startswith("//") or stripped.startswith("#"):
                continue

            # 检查事件处理器
            event_match = re.match(r"^@(\w+)", stripped, re.IGNORECASE)
            if event_match:
                event_name = event_match.group(1).lower()
                if event_name in self._event_handlers:
                    current_block = f"event_{event_name}"
                    blocks[current_block] = {
                        "type": "event",
                        "event_name": event_name,
                        "commands": [],
                        "events": [event_name],
                        "has_dialogue": False,
                        "has_combat": False,
                        "has_shop": False,
                    }
                    continue

            # 检查函数定义
            func_match = re.match(r"^function\s+(\w+)", stripped, re.IGNORECASE)
            if func_match:
                current_block = func_match.group(1)
                blocks[current_block] = {
                    "type": "function",
                    "commands": [],
                    "events": [],
                    "has_dialogue": False,
                    "has_combat": False,
                    "has_shop": False,
                }
                continue

            # 收集命令
            cmd_lower = stripped.lower()

            # 检测对话
            if "say" in cmd_lower or "message" in cmd_lower:
                blocks[current_block]["has_dialogue"] = True

            # 检测战斗
            if any(k in cmd_lower for k in ["attack", "damage", "life", "enemy", "spawn"]):
                blocks[current_block]["has_combat"] = True

            # 检测商店
            if any(k in cmd_lower for k in ["shop", "item", "buy", "sell", "money", "price"]):
                blocks[current_block]["has_shop"] = True

            blocks[current_block]["commands"].append(stripped)

        # 过滤空块
        return {k: v for k, v in blocks.items() if v["commands"]}

    def _extract_dialogues(self, commands: List[str]) -> List[str]:
        """提取对话文本"""
        dialogues = []

        for cmd in commands:
            cmd_lower = cmd.lower()

            # Say "text"
            say_match = re.match(r'say\s+["\'](.+)["\']', cmd, re.IGNORECASE)
            if say_match:
                dialogues.append(say_match.group(1))
                continue

            # ShowMessage "text"
            msg_match = re.match(r'showmessage\s+["\'](.+)["\']', cmd, re.IGNORECASE)
            if msg_match:
                dialogues.append(msg_match.group(1))
                continue

            # 引号内的文本
            text_match = re.findall(r'["\']([^"\']+)["\']', cmd)
            for text in text_match:
                if len(text) > 5 and not text.replace(".", "").replace("-", "").isdigit():
                    dialogues.append(text)

        return dialogues

    def _extract_global_dependencies(
        self,
        content: str,
        rel_path: str,
        nodes: List[ContentNode],
        graph: ContentGraph,
    ) -> None:
        """提取全局依赖关系"""
        # 检查引用的外部脚本
        script_refs = re.findall(
            r'runscript\s+["\']?([\w_\-/\\.]+)["\']?',
            content,
            re.IGNORECASE,
        )

        for script_ref in script_refs:
            ref_id = f"ref:{script_ref}"
            if not any(n.id == ref_id for n in graph.nodes):
                ref_node = ContentNode(
                    id=ref_id,
                    type=NodeType.RESOURCE,
                    name=script_ref,
                    properties={"ref_type": "script"},
                )
                graph.add_node(ref_node)

            for node in nodes:
                graph.add_edge(ContentEdge(
                    source=node.id,
                    target=ref_id,
                    type=EdgeType.REFERENCES,
                ))

    def _add_file_node(self, rel_path: str, nodes: List[ContentNode], graph: ContentGraph) -> None:
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
                graph.add_edge(ContentEdge(
                    source=file_node_id,
                    target=node.id,
                    type=EdgeType.CONTAINS,
                ))

    def _generate_node_id(self, file_path: str, block_name: str) -> str:
        """生成节点 ID"""
        safe_file = file_path.replace("/", "_").replace("\\", "_").replace(".", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", block_name)
        return f"{safe_file}_{safe_name}"
