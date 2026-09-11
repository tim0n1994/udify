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
from udify.core.cognition.target_resolver import resolve_targets_grounded
from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem
from udify.core.planning.action_schemas import ActionKind, ActionSchemaRegistry
from udify.core.planning.patch_synthesizer import PatchSynthesizer, PlannedAction
from udify.models.cdl_patch import CDLPatch
from udify.models.content_graph import ContentGraph, ContentNode


class IntentClarificationError(ValueError):
    """A plan cannot proceed until the user resolves its target or numeric instruction.

    Attributes:
        question: User-facing question persisted by the job runner.
        candidates: Current legal choices with node_id and display_name keys.
        reason: Stable reason code for the review contract.
    """

    def __init__(self, question: str, candidates: list[dict[str, str]], reason: str) -> None:
        super().__init__(question)
        self.question = question
        self.candidates = candidates
        self.reason = reason


IntentClarification = IntentClarificationError


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

    def perceive(self) -> ContentGraph:
        """阶段 1：构建带证据语义图（ADAPT-MIU2D + PER-LIFT）。

        独立暴露给 ModJob 状态机按阶段驱动（ORCH-JOB，2026-08 批次 4A）。
        """
        return self.world_builder.build(self.game_root)

    def plan(
        self, graph: ContentGraph, intent: str, *, target_ids: list[str] | None = None
    ) -> tuple[list[PlannedAction], CDLPatch | None, list[str]]:
        """阶段 2：意图 → 动作 → file_patch 计划。

        Returns:
            (actions, patch, errors)。patch 为 None 时 errors 非空。

        Raises:
            IntentClarification: 目标歧义、选择越界或数值指令不明确。
        """
        actions = self._intent_to_actions(intent, graph, target_ids=target_ids)
        if not actions:
            return [], None, ["无法从意图推导出可应用的动作"]

        ops = self.synthesizer.synthesize(graph, actions)
        if not ops:
            return actions, None, ["Patch 合成未产生任何操作"]

        patch = CDLPatch(
            operations=ops,
            intent=intent,
            author="miu2d_closed_loop",
        )
        return actions, patch, []

    def preview(self, patch: CDLPatch) -> tuple[VirtualFileSystem, list[str], str | None]:
        """阶段 3：VFS 预览（不碰原文件）。

        Returns:
            (vfs, op_errors, fatal_error)。fatal_error 非 None 表示执行器
            自身抛异常（此时 vfs 内容不可信）；op_errors 是单个操作的失败。
        """
        vfs = VirtualFileSystem(self.game_root)
        executor = PatchExecutor(vfs)
        try:
            exec_result = executor.execute(patch)
        except Exception as e:
            return vfs, [], f"VFS 执行失败: {e}"
        op_errors = [] if exec_result["success"] else [f["error"] for f in exec_result["failed"]]
        return vfs, op_errors, None

    def run(self, intent: str) -> Miu2dPlanResult:
        """执行完整闭环：自然语言 → 语义图 → file_patch 计划 → VFS 预览。"""
        result = Miu2dPlanResult(success=False)

        try:
            graph = self.perceive()
        except Exception as e:
            result.errors.append(f"感知失败: {e}")
            return result
        result.graph = graph

        try:
            actions, patch, plan_errors = self.plan(graph, intent)
        except IntentClarification as exc:
            result.errors.append(exc.question)
            return result
        result.actions = actions
        if patch is None:
            result.errors.extend(plan_errors)
            return result
        result.patch = patch

        vfs, op_errors, fatal = self.preview(patch)
        if fatal is not None:
            result.errors.append(fatal)
            return result
        result.errors.extend(op_errors)

        result.vfs_diffs = vfs.get_all_diffs()
        result.success = len(result.errors) == 0
        return result

    def _intent_to_actions(
        self, intent: str, graph: ContentGraph, *, target_ids: list[str] | None = None
    ) -> list[PlannedAction]:
        """把自然语言意图映射为针对语义图节点的 PlannedAction 列表。"""
        actions: list[PlannedAction] = []
        if any(re.search(pattern, intent, re.I) for pattern, _, _ in _INTENT_PATTERNS):
            return self._numeric_actions(intent, graph, target_ids)
        if target_ids is not None:
            raise IntentClarification(
                "此操作不支持目标选择，请重新描述修改。", [], "unsupported_selection"
            )

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

    def _numeric_actions(
        self, intent: str, graph: ContentGraph, target_ids: list[str] | None
    ) -> list[PlannedAction]:
        clauses = re.split(r"[,，;；。]|\band\b|同时|并且", intent, flags=re.I)
        exclusion = bool(re.search(r"除了|除外|不包括|排除|\bexcept\b|\bexclud\w*", intent, re.I))
        for clause in clauses:
            negative = re.search(
                r"不要|不改|别改|保持|不变|do\s+not|don't|unchanged|\bkeep\b", clause, re.I
            )
            if negative is None:
                continue
            remaining = clause[negative.end() :]
            mentions_target = any(
                node.name and re.search(re.escape(node.name), remaining, re.I)
                for node in graph.nodes
            ) or bool(
                re.search(r"boss|首领|主角|hero|player|玩家|敌人|enemy|怪物", remaining, re.I)
            )
            preserves_field = any(
                re.search(pattern, remaining, re.I) for pattern, _, _ in _INTENT_PATTERNS
            )
            exclusion = exclusion or mentions_target or not preserves_field
        if exclusion:
            raise IntentClarification(
                "暂不支持目标排除语句，请明确列出需要修改的目标后重新描述。",
                [],
                "unsupported_target_exclusion",
            )
        if resolve_targets_grounded(graph, intent).reason == "unsupported_compound_selector":
            raise IntentClarification(
                "请一次指定一个目标选择条件，或同一类别的全部目标。",
                [],
                "unsupported_compound_selector",
            )
        active = [
            clause
            for clause in clauses
            if not re.search(
                r"不要|不改|别改|保持|不变|do\s+not|don't|unchanged|\bkeep\b", clause, re.I
            )
        ]
        instruction = " ".join(active)
        if re.search(
            r"[-−]\s*\d|(?:增加|减少)\s*\d.*倍|删除|新增|添加|\b(?:delete|remove|add)\b",
            instruction,
            re.I,
        ):
            raise IntentClarification(
                "请把数值缩放和其他修改分别描述，并使用明确的目标倍数。",
                [],
                "unsupported_numeric_instruction",
            )
        mutation = re.sub(
            r"(?:血量|生命|hp|攻击|attack)\s*(?:最[高低多少]|max|min)|"
            r"(?:highest|lowest|max|min)\s*(?:hp|health|attack)",
            "",
            instruction,
            flags=re.I,
        )
        matches = [
            (schema, defaults)
            for pattern, schema, defaults in _INTENT_PATTERNS
            if re.search(pattern, mutation, re.I)
        ]
        if len(matches) != 1:
            raise IntentClarification(
                "请一次指定一个要修改的数值，以及明确的倍数。",
                [],
                "unsupported_numeric_instruction",
            )
        for clause in clauses:
            if clause in active:
                continue
            if any(
                schema == matches[0][0] and re.search(pattern, clause, re.I)
                for pattern, schema, _ in _INTENT_PATTERNS
            ):
                raise IntentClarification(
                    "同一数值同时要求修改和保持不变，请明确需要保留的约束。",
                    [],
                    "conflicting_numeric_constraint",
                )
        factors = [
            float(a or b)
            for a, b in re.findall(
                r"(\d+(?:\.\d+)?)\s*倍|(?:\bx|×|\*)\s*(\d+(?:\.\d+)?)", instruction, re.I
            )
        ]
        if re.search(r"翻倍|\bdouble\b", instruction, re.I):
            factors.append(2.0)
        if re.search(r"减半|\bhalf\b|\bhalve\b", instruction, re.I):
            factors.append(0.5)
        if len(factors) != 1:
            raise IntentClarification(
                "请指定一个明确倍数，例如翻倍、减半或 1.5 倍。",
                [],
                "unsupported_numeric_instruction",
            )
        factor = factors[0]
        schema_name, defaults = matches[0]
        params = {**defaults, "factor": factor}
        applicable = {}
        for node in graph.nodes:
            schemas = self.schemas.find_applicable(
                tuple(node.semantic_tags),
                numeric_kind=params.get("numeric_kind"),
                kind=ActionKind.NUMERIC_SCALE,
            )
            schema = next((item for item in schemas if item.name == schema_name), None)
            if schema is not None:
                applicable[node.id] = (node, schema)
        resolution = resolve_targets_grounded(graph, instruction)
        target_description = instruction
        if not resolution.candidates and not re.search(
            r"boss|首领|头目|主角|hero|player|玩家|敌人|enemy|enemies|怪物", instruction, re.I
        ):
            prefixes = [
                re.split(r"不要|不改|别改|do\s+not|don't", clause, flags=re.I)[0]
                for clause in clauses
                if clause not in active
                and re.search(r"不要|不改|别改|do\s+not|don't", clause, re.I)
            ]
            target_description = " ".join(prefixes + [instruction])
            resolution = resolve_targets_grounded(graph, target_description)
        candidate_ids = {
            candidate.node_id for candidate in resolution.candidates
        } & applicable.keys()
        if not resolution.candidates and not re.search(
            r"boss|首领|头目|主角|hero|player|玩家|敌人|enemy|enemies|怪物",
            target_description,
            re.I,
        ):
            candidate_ids = set(applicable)
        candidates = [
            {"node_id": node.id, "display_name": node.name or node.id}
            for node in graph.nodes
            if node.id in candidate_ids
        ]
        if target_ids is not None:
            if (
                not target_ids
                or len(set(target_ids)) != len(target_ids)
                or not set(target_ids) <= candidate_ids
            ):
                raise IntentClarification(
                    "所选目标已失效或不符合意图，请重新选择。", candidates, "invalid_selection"
                )
            chosen_ids = set(target_ids)
        elif resolution.ambiguous or not resolution.chosen_ids():
            raise IntentClarification(
                "请选择要修改的目标。", candidates, resolution.reason or "target_required"
            )
        else:
            chosen_ids = set(resolution.chosen_ids())
            if not chosen_ids <= candidate_ids:
                raise IntentClarification(
                    "目标没有可修改的指定数值。", candidates, "unsupported_target"
                )
        actions = []
        for node, schema in applicable.values():
            if node.id not in chosen_ids:
                continue
            if not self._check_constraint(factor, schema.constraints):
                raise IntentClarification(
                    "倍数超出该数值允许的范围。", candidates, "factor_out_of_range"
                )
            numeric_key = self._requested_numeric_key(node, mutation, str(params["numeric_kind"]))
            if numeric_key is None:
                raise IntentClarification(
                    f"{node.name} 缺少唯一可识别的目标数值，请明确字段。",
                    candidates,
                    "missing_numeric_property",
                )
            actions.append(
                PlannedAction(
                    schema_name=schema_name,
                    target_node_id=node.id,
                    params={**params, "numeric_key": numeric_key},
                    reason=f"意图「{intent}」→ {schema_name} factor={factor}; "
                    + "; ".join(
                        reason
                        for candidate in resolution.candidates
                        if candidate.node_id == node.id
                        for reason in candidate.reasons
                    ),
                )
            )
        return actions

    def _requested_numeric_key(self, node: ContentNode, instruction: str, kind: str) -> str | None:
        from udify.core.perception.semantic_lifter import _NUMERIC_ATTRIBUTES, _norm

        numeric_keys = [
            key
            for key, value in node.properties.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        explicit_keys = [
            key
            for key in numeric_keys
            if re.search(r"(?<![a-z0-9_])" + re.escape(key) + r"(?![a-z0-9_])", instruction, re.I)
        ]
        if explicit_keys:
            return explicit_keys[0] if len(explicit_keys) == 1 else None
        matching = [key for key in numeric_keys if _NUMERIC_ATTRIBUTES.get(_norm(key)) == kind]
        return matching[0] if len(matching) == 1 else None

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

    def _first_tagged_node(self, graph: ContentGraph, tags: tuple[str, ...]) -> ContentNode | None:
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


__all__ = ["IntentClarification", "Miu2dClosedLoop", "Miu2dPlanResult"]
