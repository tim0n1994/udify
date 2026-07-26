"""
miu2d 闭环编排器（批次 2 验收）。

对应 ITERATION-PLAN-2026-07.md 批次 2：把 ADAPT-MIU2D + PER-LIFT + PLAN-ACTION
+ PATCH-SYN 串成一条真实闭环：

    自然语言意图
      → 带证据语义图（GameWorldGraphBuilder：感知 + 语义提升 + 关系推断）
      → file_patch 计划（ActionSchemaRegistry 匹配 + PatchSynthesizer 合成）
      → VFS 预览（PatchExecutor 应用，不碰原文件）

这是批次 2 的北极星片段（批次 3 才补 Playwright 运行时探针与 UdifyBench）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.adapters.miu2d_world import GameWorldGraphBuilder
from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem
from udify.core.planning.action_schemas import ActionKind, ActionSchemaRegistry
from udify.core.planning.patch_synthesizer import PatchSynthesizer, PlannedAction
from udify.models.cdl_patch import CDLPatch
from udify.models.content_graph import ContentGraph


@dataclass
class Miu2dPlanResult:
    """miu2d 闭环结果。"""

    success: bool
    graph: ContentGraph | None = None
    patch: CDLPatch | None = None
    vfs_diffs: list[dict[str, Any]] = field(default_factory=list)
    actions: list[PlannedAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# 意图 → 动作意图的简单映射（批次 3 会由 Intent Compiler 替代）
_INTENT_PATTERNS: list[tuple[str, str, dict[str, Any]]] = [
    # (正则, schema_name, 默认参数)
    (r"血量|hp|生命|life|maxlife", "scale_health", {"factor": 2.0, "numeric_kind": "health"}),
    (r"攻击|伤害|attack|damage|atk", "scale_offense", {"factor": 1.5, "numeric_kind": "offense"}),
    (r"防御|defense|def", "scale_defense", {"factor": 1.5, "numeric_kind": "defense"}),
    (r"掉落|drop|掉率", "scale_drop_rate", {"factor": 2.0, "numeric_kind": "drop"}),
    (r"经验|exp|经验值", "scale_experience", {"factor": 2.0, "numeric_kind": "experience"}),
    (
        r"削弱|nerf|治疗|potion|道具效果|value|价格|price",
        "scale_currency",
        {"factor": 0.5, "numeric_kind": "currency"},
    ),
]


class Miu2dClosedLoop:
    """miu2d 单条黄金闭环编排器。"""

    def __init__(self, game_root: Path) -> None:
        self.game_root = game_root
        self.world_builder = GameWorldGraphBuilder()
        self.schemas = ActionSchemaRegistry()
        self.synthesizer = PatchSynthesizer()

    def run(self, intent: str) -> Miu2dPlanResult:
        """执行完整闭环：自然语言 → 语义图 → file_patch 计划 → VFS 预览。"""
        result = Miu2dPlanResult(success=False)

        # 1. 带证据语义图（ADAPT-MIU2D + PER-LIFT）
        try:
            graph = self.world_builder.build(self.game_root)
        except Exception as e:
            result.errors.append(f"感知失败: {e}")
            return result
        result.graph = graph

        # 2. 意图 → 动作（PLAN-ACTION 匹配）
        actions = self._intent_to_actions(intent, graph)
        if not actions:
            result.errors.append("无法从意图推导出可应用的动作")
            return result
        result.actions = actions

        # 3. file_patch 计划（PATCH-SYN 合成）
        ops = self.synthesizer.synthesize(graph, actions)
        if not ops:
            result.errors.append("Patch 合成未产生任何操作")
            return result

        patch = CDLPatch(
            operations=ops,
            intent=intent,
            author="miu2d_closed_loop",
        )
        result.patch = patch

        # 4. VFS 预览（不碰原文件）
        vfs = VirtualFileSystem(self.game_root)
        executor = PatchExecutor(vfs)
        try:
            exec_result = executor.execute(patch)
            if not exec_result["success"]:
                result.errors.extend(f["error"] for f in exec_result["failed"])
        except Exception as e:
            result.errors.append(f"VFS 执行失败: {e}")
            return result

        result.vfs_diffs = vfs.get_all_diffs()
        result.success = len(result.errors) == 0
        return result

    def _intent_to_actions(self, intent: str, graph: ContentGraph) -> list[PlannedAction]:
        """把自然语言意图映射为针对语义图节点的 PlannedAction 列表。"""
        actions: list[PlannedAction] = []
        intent_lower = intent.lower()

        # 解析"翻倍/×N"等倍数
        factor = 2.0
        m = re.search(r"(\d+(?:\.\d+)?)\s*倍", intent)
        if m:
            factor = float(m.group(1))
        elif "翻倍" in intent:
            factor = 2.0
        elif "减半" in intent:
            factor = 0.5

        for pattern, schema_name, defaults in _INTENT_PATTERNS:
            if re.search(pattern, intent_lower):
                params = dict(defaults)
                params["factor"] = factor
                # 找到目标节点（带匹配标签 + 数值类别）
                for node in graph.nodes:
                    if not node.semantic_tags:
                        continue
                    # schema 要求的标签
                    applicable = self.schemas.find_applicable(
                        tuple(node.semantic_tags),
                        numeric_kind=params.get("numeric_kind"),
                        kind=ActionKind.NUMERIC_SCALE,
                    )
                    target_schema = next((s for s in applicable if s.name == schema_name), None)
                    if target_schema is None:
                        continue
                    # 约束检查
                    if not self._check_constraint(factor, target_schema.constraints):
                        # factor 超出 schema 约束（如 >5.0），跳过该节点
                        continue
                    actions.append(
                        PlannedAction(
                            schema_name=schema_name,
                            target_node_id=node.id,
                            params=params,
                            reason=f"意图「{intent}」→ {schema_name} factor={factor}",
                        )
                    )
                break  # 一个意图模式匹配即可

        # 内容新增类意图（优先于 DSL，因为 "新增商店物品" 应产生 ADD）
        if not actions:
            content_actions = self._intent_to_content_actions(intent, graph)
            actions.extend(content_actions)

        # DSL 奖励类意图（技能/物品/金币奖励）
        if not actions:
            dsl_actions = self._intent_to_dsl_actions(intent, graph)
            actions.extend(dsl_actions)

        # 脚本效果类意图（安全脚本插入）
        if not actions:
            script_actions = self._intent_to_script_actions(intent, graph)
            actions.extend(script_actions)

        return actions

    def _intent_to_dsl_actions(self, intent: str, graph: ContentGraph) -> list[PlannedAction]:
        """把奖励/技能/对话类意图映射为 DSL 命令动作。"""
        actions: list[PlannedAction] = []
        intent_lower = intent.lower()
        from udify.core.adapters.miu2d_dsl import DslCommandRegistry

        _dsl = DslCommandRegistry()  # 校验用（命令合法性由 synthesizer 再查一次）
        # 技能奖励
        if any(w in intent_lower for w in ["技能", "skill", "法术"]):
            target = self._first_tagged_node(
                graph, ("npc", "character", "quest", "boss", "player", "enemy")
            )
            if target:
                actions.append(
                    PlannedAction(
                        schema_name="dsl_command",
                        target_node_id=target.id,
                        params={"command": "GiveSkill", "args": ["new_skill", 1]},
                        reason=f"意图「{intent}」→ GiveSkill",
                    )
                )
        # 物品奖励/新增物品
        elif any(w in intent_lower for w in ["物品", "item", "商店", "shop", "新增"]):
            target = self._first_tagged_node(graph, ("npc", "character", "item"))
            if target:
                actions.append(
                    PlannedAction(
                        schema_name="dsl_command",
                        target_node_id=target.id,
                        params={"command": "GiveItem", "args": ["new_item", 1]},
                        reason=f"意图「{intent}」→ GiveItem",
                    )
                )
        # 金币
        elif any(w in intent_lower for w in ["金币", "gold", "钱"]):
            target = self._first_tagged_node(graph, ("boss", "enemy", "npc"))
            if target:
                actions.append(
                    PlannedAction(
                        schema_name="dsl_command",
                        target_node_id=target.id,
                        params={"command": "GiveGold", "args": [100]},
                        reason=f"意图「{intent}」→ GiveGold",
                    )
                )
        return actions

    def _intent_to_content_actions(self, intent: str, graph: ContentGraph) -> list[PlannedAction]:
        """把内容增删/可达性类意图映射为动作。"""
        actions: list[PlannedAction] = []
        intent_lower = intent.lower()
        # "新增商店物品" / "添加" → ADD_NODE 类内容新增
        if any(w in intent_lower for w in ["新增", "添加", "add", "商店", "shop"]):
            target = self._first_tagged_node(graph, ("item", "character", "npc"))
            if target:
                actions.append(
                    PlannedAction(
                        schema_name="add_content",
                        target_node_id=target.id,
                        params={
                            "key": "ShopItem",
                            "value": "new_shop_entry",
                            "op_type": "ADD",
                        },
                        reason=f"意图「{intent}」→ add content",
                    )
                )
        # 可达性保持：不删除节点（映射为对现有节点的安全数值调整）
        elif any(w in intent_lower for w in ["可达", "reachab", "保持", "难度"]):
            # 落到数值调整（保持可达 = 不破坏结构）
            for node in graph.nodes:
                if "boss" in node.semantic_tags or "enemy" in node.semantic_tags:
                    actions.append(
                        PlannedAction(
                            schema_name="scale_health",
                            target_node_id=node.id,
                            params={"factor": 1.1, "numeric_kind": "health"},
                            reason=f"意图「{intent}」→ 轻微调整（保持可达性）",
                        )
                    )
                    break
        return actions

    def _intent_to_script_actions(self, intent: str, graph: ContentGraph) -> list[PlannedAction]:
        """把脚本效果类意图映射为安全的 Lua 插入。"""
        actions: list[PlannedAction] = []
        intent_lower = intent.lower()
        if any(w in intent_lower for w in ["脚本", "script", "效果", "effect", "加"]):
            # 找一个脚本节点或角色节点
            target = self._first_tagged_node(graph, ("script", "character", "boss"))
            if target:
                actions.append(
                    PlannedAction(
                        schema_name="insert_script",
                        target_node_id=target.id,
                        params={
                            "location": "",
                            "body": "-- safe effect: print debug\nprint('mod applied')",
                        },
                        reason=f"意图「{intent}」→ safe script insert",
                    )
                )
        return actions

    def _first_tagged_node(self, graph: ContentGraph, tags: tuple[str, ...]):
        """找第一个带指定标签的节点。"""
        for node in graph.nodes:
            if any(t in node.semantic_tags for t in tags):
                return node
        return None

    def _check_constraint(self, factor: float, constraints: tuple[str, ...]) -> bool:
        """约束检查：解析约束中所有 ``factor OP N`` 子表达式（支持复合约束如
        ``0.1 <= factor <= 5.0``）。"""
        from udify.core.text_normalize import iter_constraints

        for c in constraints:
            for expr in iter_constraints(c):
                if expr.attr == "factor" and not expr.evaluate(factor):
                    return False
        return True


__all__ = ["Miu2dClosedLoop", "Miu2dPlanResult"]
