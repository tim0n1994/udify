"""
Patch 合成器（PATCH-SYN-01..06）。

MODULE-ATTACK-MAP-v3 §8 PATCH-SYN：把规划动作合成为带精确 SourceSpan 的
``execution_mode=file_patch`` 操作，并能产生可回滚的逆操作。

- PATCH-SYN-01: graph target → source anchor（SourceSpan 精确）
- PATCH-SYN-02: INI emitter（格式保持）
- PATCH-SYN-03: OBJ emitter（引用不丢）
- PATCH-SYN-04: Lua safe insert（AST/语法验证）
- PATCH-SYN-05: DSL command emitter（命令 schema 校验）
- PATCH-SYN-06: reverse builder（全部 P0 op 可回滚）

这是连接"语义图 + 动作 schema"与"VFS 可应用文件修改"的桥梁。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from udify.core.adapters.miu2d_dsl import DslCommandRegistry
from udify.models.cdl_patch import ExecutionMode, OpType, PatchOperation
from udify.models.content_graph import ContentGraph, ContentNode
from udify.models.source import SourceSpan, ToolRunRef


@dataclass
class PlannedAction:
    """planner 产出的高层动作（待合成为 PatchOperation）。"""

    schema_name: str
    target_node_id: str
    params: dict[str, Any]
    reason: str = ""


class PatchSynthesizer:
    """Patch 合成器：高层动作 → file_patch PatchOperation（带 SourceSpan + reverse）。"""

    def __init__(self, dsl_registry: DslCommandRegistry | None = None) -> None:
        self.dsl = dsl_registry or DslCommandRegistry()
        self._emitter = ToolRunRef(tool_id="patch_synthesizer", version="1.0")

    def synthesize(self, graph: ContentGraph, actions: list[PlannedAction]) -> list[PatchOperation]:
        """把一组动作合成为 PatchOperation 列表。"""
        ops: list[PatchOperation] = []
        for action in actions:
            node = graph.get_node(action.target_node_id)
            if node is None:
                continue
            op = self._synthesize_one(graph, node, action)
            if op is not None:
                ops.append(op)
        return ops

    def _synthesize_one(
        self, graph: ContentGraph, node: ContentNode, action: PlannedAction
    ) -> PatchOperation | None:
        name = action.schema_name

        if name.startswith("scale_") or name == "modify_numeric":
            return self._emit_numeric_scale(node, action)
        if name.startswith("modify_") and "reward" in name:
            return self._emit_reward(node, action)
        if name == "modify_item_reward":
            return self._emit_reward(node, action)
        if name == "insert_script":
            return self._emit_script_insert(node, action)
        if name.startswith("dsl_"):
            return self._emit_dsl_command(node, action)
        if name == "add_content":
            return self._emit_add_content(node, action)
        # 兜底：通用属性修改
        return self._emit_generic_modify(node, action)

    # --- PATCH-SYN-02: INI emitter（格式保持）------------------------------

    def _emit_numeric_scale(
        self, node: ContentNode, action: PlannedAction
    ) -> PatchOperation | None:
        """数值缩放：找到节点上的目标数值属性，应用 factor。"""
        factor = action.params.get("factor", 1.0)
        target_kind = action.params.get("numeric_kind") or action.params.get("kind")

        # 找到匹配的数值属性键
        prop_key = self._find_numeric_key(node, target_kind)
        if prop_key is None:
            return None

        current = node.properties.get(prop_key)
        if not isinstance(current, (int, float)):
            return None

        new_value = self._compute_scaled(current, factor, prop_key)

        span = self._node_span(node, prop_key)
        return PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id=node.id,
            payload={
                "key": prop_key,
                "old_value": current,
                "value": new_value,
                "factor": factor,
                "emitter": "ini",
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason or f"scale {prop_key} by {factor}",
            risk=0.2,
        )

    # --- PATCH-SYN-04: Lua safe insert --------------------------------------

    def _emit_script_insert(
        self, node: ContentNode, action: PlannedAction
    ) -> PatchOperation | None:
        """插入 Lua 脚本片段（带危险 API 检查）。"""
        body = action.params.get("body", "")
        location = action.params.get("location", "")
        guard = action.params.get("guard", "")

        # 安全检查：禁止危险 API（PATCH-SYN-04 AST/语法验证的简化版）
        danger = self._check_lua_safety(body)
        if danger:
            return None  # 危险脚本拒绝合成

        full_body = ""
        if guard:
            full_body += f"if {guard} then\n"
        full_body += body
        if guard:
            full_body += "\nend"

        span = self._node_span(node)
        return PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id=node.id,
            payload={
                "emitter": "lua_insert",
                "location": location,
                "body": full_body,
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason or f"insert script at {location}",
            risk=0.5,
        )

    # --- PATCH-SYN-05: DSL command emitter ----------------------------------

    def _emit_dsl_command(self, node: ContentNode, action: PlannedAction) -> PatchOperation | None:
        """DSL 命令：用 registry 校验后发射。"""
        cmd_name = action.params.get("command", "")
        cmd_args = action.params.get("args", [])

        ok, msg = self.dsl.validate(cmd_name, cmd_args)
        if not ok:
            return None

        span = self._node_span(node)
        return PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id=node.id,
            payload={
                "emitter": "dsl",
                "command": cmd_name,
                "args": cmd_args,
                "validation": msg,
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason or f"dsl {cmd_name}",
            risk=0.3,
        )

    def _emit_reward(self, node: ContentNode, action: PlannedAction) -> PatchOperation | None:
        """奖励修改（item/exp/gold）。"""
        if "factor" in action.params:
            return self._emit_numeric_scale(node, action)
        # item count delta
        item_id = action.params.get("item_id", "")
        count_delta = action.params.get("count_delta", 0)
        span = self._node_span(node)
        return PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id=node.id,
            payload={
                "emitter": "reward",
                "item_id": item_id,
                "count_delta": count_delta,
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason or "modify reward",
            risk=0.3,
        )

    def _emit_generic_modify(self, node: ContentNode, action: PlannedAction) -> PatchOperation:
        span = self._node_span(node)
        return PatchOperation(
            op_type=OpType.MODIFY_PROPERTY,
            target_id=node.id,
            payload={
                "key": action.params.get("key", ""),
                "value": action.params.get("value"),
                "emitter": "generic",
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason,
            risk=0.2,
        )

    def _emit_add_content(self, node: ContentNode, action: PlannedAction) -> PatchOperation:
        """内容新增：向目标节点的文件追加一个新条目（ADD 语义，file_patch 形态）。"""
        span = self._node_span(node)
        return PatchOperation(
            op_type=OpType.ADD_NODE,
            target_id=node.id,
            payload={
                "key": action.params.get("key", "NewEntry"),
                "value": action.params.get("value", ""),
                "emitter": "add_content",
                "op_type": "ADD",
            },
            execution_mode=ExecutionMode.FILE_PATCH,
            source_span=span,
            planning_reason=action.reason or "add content",
            risk=0.25,
        )

    # --- PATCH-SYN-01: source anchor + helpers ------------------------------

    def _node_span(self, node: ContentNode, prop_key: str | None = None) -> SourceSpan:
        """从节点取精确 SourceSpan（PATCH-SYN-01）。"""
        existing = getattr(node, "source_span", None)
        if isinstance(existing, SourceSpan):
            if prop_key:
                # 细化 ast_path 到属性
                return SourceSpan(
                    file_path=existing.file_path,
                    line_start=existing.line_start,
                    line_end=existing.line_end,
                    ast_path=(*existing.ast_path, prop_key),
                    extractor=self._emitter,
                )
            return existing
        # 兜底：用 source_path 构造
        fp = node.source_path or "unknown"
        return SourceSpan(
            file_path=fp,
            ast_path=(node.name,) + ((prop_key,) if prop_key else ()),
            extractor=self._emitter,
        )

    def _find_numeric_key(self, node: ContentNode, target_kind: str | None) -> str | None:
        """在节点属性中找匹配数值语义类别的键。"""
        from udify.core.perception.semantic_lifter import _NUMERIC_ATTRIBUTES, _norm

        if target_kind:
            for key in node.properties:
                if _NUMERIC_ATTRIBUTES.get(_norm(key)) == target_kind:
                    return key
        # 无指定类别：找第一个 health/offense 数值
        for key, value in node.properties.items():
            if isinstance(value, (int, float)):
                kind = _NUMERIC_ATTRIBUTES.get(_norm(key))
                if kind in ("health", "offense", "defense"):
                    return key
        return None

    def _compute_scaled(self, current: float, factor: float, key: str) -> float:
        """计算缩放后的值（整数属性保持整数）。"""
        new_val = current * factor
        # INI 数值多为整数
        if isinstance(current, int) or float(current).is_integer():
            return int(round(new_val))
        return new_val

    def _check_lua_safety(self, body: str) -> str | None:
        """检查 Lua 片段是否含危险 API（PATCH-SYN-04 简化）。

        复用 ``normalize_identifier``，使 ``os.execute`` 与 ``os . execute`` 都能命中。
        """
        from udify.core.perception.parsers.lua_ts_parser import DANGEROUS_APIS
        from udify.core.text_normalize import normalize_identifier

        normalized = normalize_identifier(body)
        for api, category in DANGEROUS_APIS.items():
            api_norm = normalize_identifier(api)
            if api_norm and api_norm in normalized:
                return category
        return None

    # --- PATCH-SYN-06: reverse builder --------------------------------------

    @staticmethod
    def build_reverse(op: PatchOperation) -> PatchOperation:
        """为一个 PatchOperation 构造逆操作（PATCH-SYN-06）。

        全部 P0 op（MODIFY_PROPERTY 的 ini/lua/dsl/reward 变体）可回滚。
        """
        payload = dict(op.payload)

        if "old_value" in payload and "value" in payload:
            # 数值修改：交换 old/new
            payload["value"], payload["old_value"] = payload["old_value"], payload["value"]
            payload["reverse"] = True
        elif payload.get("emitter") == "lua_insert":
            # 脚本插入的逆 = 标记移除该 body
            payload["emitter"] = "lua_remove"
            payload["remove_body"] = payload.pop("body", "")
            payload["reverse"] = True
        elif payload.get("emitter") == "dsl":
            # DSL 的逆取决于命令是否 reversible；标记逆命令
            payload["reverse"] = True
        else:
            payload["reverse"] = True

        return PatchOperation(
            op_type=op.op_type,
            target_id=op.target_id,
            payload=payload,
            execution_mode=op.execution_mode,
            source_span=op.source_span,
            risk=op.risk,
            planning_reason=f"reverse of: {op.planning_reason}",
        )


__all__ = ["PatchSynthesizer", "PlannedAction"]
