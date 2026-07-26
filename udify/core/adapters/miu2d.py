"""
miu2d 引擎适配器（ADAPT-MIU2D-01..09 的门面层）。

对应 ITERATION-PLAN-2026-07.md §4.2。这是**复用而非重写**——把现有
``perception/parsers/*``（ini/obj/npc/lua）包装成一个实现 ``EngineAdapter``
协议的门面，输出带 ``SourceSpan`` 的节点，并补齐动作 schema / 打包能力。

注意（计划 §4.2）：Lua 的 Tree-sitter 集成（``ADAPT-MIU2D-04``）属批次 2，
本批次先用现有 ``lua_parser``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.adapters.base import DetectionResult, span_for_node
from udify.core.perception.parsers import INIParser, LuaParser, NPCScriptParser, OBJParser
from udify.models.cdl_patch import ExecutionMode, OpType, PatchOperation, create_modify_property_op
from udify.models.content_graph import ContentGraph, NodeType
from udify.models.source import Confidence, SourceSpan, ToolRunRef

MIU2D_SIGNATURE_FILES = ("characters.ini", "items.ini")
MIU2D_EXTENSIONS = (".ini", ".obj", ".npc", ".txt", ".lua", ".asf", ".msf", ".mpc", ".map", ".mmf")


@dataclass
class Miu2dAdapter:
    """miu2d 引擎适配器（实现 EngineAdapter 协议）。

    复用现有解析器，在其输出上叠加 SourceSpan 与置信度，让 miu2d 感知结果
    满足证据链要求（成功判据 #2）。
    """

    _engine_id: str = field(default="miu2d", init=False)
    _parser_version: str = field(default="1.0", init=False)

    @property
    def engine_id(self) -> str:
        return self._engine_id

    def detect(self, game_root: Path) -> DetectionResult:
        """检测是否为 miu2d 游戏：以签名文件 / 扩展名命中数衡量置信度。"""
        hits = 0
        evidence: list[str] = []
        for sig in MIU2D_SIGNATURE_FILES:
            if (game_root / sig).exists():
                hits += 2
                evidence.append(f"signature file: {sig}")
        # 扩展名命中
        ext_hits = 0
        for p in game_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in MIU2D_EXTENSIONS:
                ext_hits += 1
        if ext_hits:
            hits += min(ext_hits, 3)
            evidence.append(f"{ext_hits} miu2d-extension files")

        score = min(1.0, hits / 5.0)
        return DetectionResult(
            engine_id=self._engine_id,
            confidence=Confidence(
                score=score,
                method="signature_files" if score > 0 else "unknown",
            ),
            evidence=evidence,
            supported_operations=[
                "modify_property",
                "modify_numeric_range",
                "add_content",
                "remove_content",
            ],
        )

    def perceive(self, game_root: Path) -> ContentGraph:
        """感知 game_root，复用现有解析器并为节点补 SourceSpan + confidence。"""
        graph = ContentGraph()
        graph.source_path = str(game_root)

        ini = INIParser()
        obj = OBJParser()
        npc = NPCScriptParser()
        lua = LuaParser()
        extractor = ToolRunRef(tool_id="miu2d_parsers", version=self._parser_version)

        for root, _, files in _walk(game_root):
            for filename in files:
                file_path = Path(root) / filename
                rel_path = str(file_path.relative_to(game_root))
                ext = file_path.suffix.lower()
                before = len(graph.nodes)

                if ext == ".ini":
                    ini.parse(file_path, rel_path, graph)
                elif ext == ".obj":
                    obj.parse(file_path, rel_path, graph)
                elif ext in (".txt", ".npc"):
                    npc.parse(file_path, rel_path, graph)
                elif ext == ".lua":
                    lua.parse(file_path, rel_path, graph)

                # 为本次新增节点补证据链
                for node in graph.nodes[before:]:
                    if node.source_path == rel_path or node.source_path is None:
                        node.source_span = SourceSpan(
                            file_path=rel_path,
                            extractor=extractor,
                            ast_path=(node.name,),
                        )
                        node.confidence = Confidence(score=0.9, method="parser")
                        node.provenance = None  # 可由上层补全
        return graph

    def get_action_schemas(self) -> list[dict[str, Any]]:
        """miu2d 支持的动作 schema（供 planner/action_space 剪枝）。"""
        return [
            {
                "action": "modify_property",
                "execution_mode": ExecutionMode.FILE_PATCH.value,
                "params": {"target_id": "str", "key": "str", "value": "number|str"},
                "risk_hint": 0.2,
            },
            {
                "action": "modify_numeric_range",
                "execution_mode": ExecutionMode.FILE_PATCH.value,
                "params": {"target_id": "str", "key": "str", "min": "number", "max": "number"},
                "risk_hint": 0.3,
            },
        ]

    def emit_patch(
        self, graph: ContentGraph, actions: list[dict[str, Any]]
    ) -> list[PatchOperation]:
        """把高层动作字典发射为 miu2d 的 PatchOperation（带 execution_mode=file_patch）。"""
        ops: list[PatchOperation] = []
        for action in actions:
            kind = action.get("action") or action.get("type")
            if kind == "modify_property":
                ops.append(
                    PatchOperation(
                        op_type=OpType.MODIFY_PROPERTY,
                        target_id=action["target_id"],
                        payload={"key": action["key"], "value": action["value"]},
                        execution_mode=ExecutionMode.FILE_PATCH,
                        planning_reason=action.get("reason", ""),
                        risk=float(action.get("risk_hint", 0.2)),
                        source_span=span_for_node(
                            action.get("file_path", "unknown"), action["target_id"], "miu2d_adapter"
                        ),
                    )
                )
            else:
                # 未知动作类型，退化为通用 modify_property
                ops.append(
                    create_modify_property_op(
                        node_id=action.get("target_id", ""),
                        key=action.get("key", ""),
                        value=action.get("value"),
                    )
                )
        return ops

    def build_runtime_probes(self, graph: ContentGraph) -> list[dict[str, Any]]:
        """为运行时验证构造探针规格（批次 3 落地真实 Playwright probe）。"""
        probes: list[dict[str, Any]] = []
        # 为每个 CHARACTER 节点建议一个"启动后属性可读"探针
        for node in graph.get_nodes_by_type(NodeType.CHARACTER):
            probes.append(
                {
                    "probe_id": f"probe_{node.id}",
                    "kind": "read_state",
                    "target_node": node.id,
                    "expect": {"name": node.name},
                    "status": "suggested",  # 批次 3 才真正执行
                }
            )
        return probes

    def package_mod(
        self, graph: ContentGraph, patch_ops: list[PatchOperation], output_dir: Path
    ) -> Path:
        """把 patch 打包成 miu2d ModPackage（JSON manifest + 待写文件清单）。"""
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "engine": self._engine_id,
            "operations": [
                {
                    "op_type": op.op_type.name,
                    "target_id": op.target_id,
                    "payload": op.payload,
                    "execution_mode": op.execution_mode.value,
                }
                for op in patch_ops
            ],
            "graph_checksum": graph.checksum(),
        }
        out = output_dir / "miu2d_mod.json"
        out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        return out


def _walk(game_root: Path):
    """os.walk 的轻量包装，便于测试注入。"""
    import os

    return os.walk(game_root)


__all__ = ["Miu2dAdapter"]
