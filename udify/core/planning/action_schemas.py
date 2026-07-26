"""
动作 Schema（PLAN-ACTION-01..04）。

MODULE-ATTACK-MAP-v3 §7 PLAN-ACTION：定义 planner 可消费的结构化动作 schema，
替代现在 action_space 里脆弱的关键词匹配。

- PLAN-ACTION-01: ActionSchema 定义（target type、params、constraints）
- PLAN-ACTION-02: numeric scale schema（HP/MP/ATK/drop 等）
- PLAN-ACTION-03: script insert schema（location、guard、body）
- PLAN-ACTION-04: reward modify schema（item/exp/gold）

每个 schema 描述"对一个带语义标签的目标节点做什么修改"，planner 用它把意图
映射成具体可执行的 PatchOperation。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from udify.models.cdl_patch import ExecutionMode


class ActionKind(Enum):
    """动作类别。"""

    NUMERIC_SCALE = "numeric_scale"  # 缩放数值（HP/MP/ATK/drop）
    NUMERIC_SET = "numeric_set"  # 设定数值
    SCRIPT_INSERT = "script_insert"  # 插入脚本片段
    REWARD_MODIFY = "reward_modify"  # 修改奖励（item/exp/gold）
    CONTENT_ADD = "content_add"
    CONTENT_REMOVE = "content_remove"


@dataclass(frozen=True)
class ActionSchema:
    """单个动作 schema（PLAN-ACTION-01）。

    Attributes:
        kind: 动作类别。
        name: 人类可读名称。
        target_tags: 目标节点需具备的语义标签（如 ``("boss","tunable")``）。
        target_numeric_kind: 目标需具备的数值语义类别（如 ``health``），可选。
        params: 参数定义（名称 → 类型字符串）。
        constraints: 约束表达式（如 ``"factor <= 1.35"``）。
        execution_mode: 产生 patch 的执行形态。
        risk: 启发式风险分（0-1）。
    """

    kind: ActionKind
    name: str
    target_tags: tuple[str, ...] = field(default_factory=tuple)
    target_numeric_kind: str | None = None
    params: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    constraints: tuple[str, ...] = field(default_factory=tuple)
    execution_mode: ExecutionMode = ExecutionMode.FILE_PATCH
    risk: float = 0.2


# --- PLAN-ACTION-02: numeric scale schemas ----------------------------------

NUMERIC_SCALE_SCHEMAS: list[ActionSchema] = [
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_health",
        target_tags=("boss", "enemy", "player", "character"),
        target_numeric_kind="health",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 5.0",),
        risk=0.2,
    ),
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_offense",
        target_tags=("boss", "enemy", "player", "character"),
        target_numeric_kind="offense",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 5.0",),
        risk=0.3,
    ),
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_defense",
        target_tags=("boss", "enemy", "player", "character"),
        target_numeric_kind="defense",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 5.0",),
        risk=0.3,
    ),
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_drop_rate",
        target_tags=("boss", "enemy"),
        target_numeric_kind="drop",
        params=(("factor", "float"),),
        constraints=("0.0 <= factor <= 10.0",),
        risk=0.35,
    ),
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_experience",
        target_tags=("boss", "enemy"),
        target_numeric_kind="experience",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 10.0",),
        risk=0.25,
    ),
    ActionSchema(
        kind=ActionKind.NUMERIC_SCALE,
        name="scale_currency",
        target_tags=("item", "boss", "enemy", "npc", "character"),
        target_numeric_kind="currency",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 10.0",),
        risk=0.25,
    ),
]


# --- PLAN-ACTION-03: script insert schema -----------------------------------

SCRIPT_INSERT_SCHEMA = ActionSchema(
    kind=ActionKind.SCRIPT_INSERT,
    name="insert_script",
    target_tags=("script", "lua_function"),
    params=(
        ("location", "str"),  # 函数名/锚点
        ("guard", "str"),  # 插入前的守卫条件（可选）
        ("body", "str"),  # Lua 代码片段
    ),
    constraints=("no_dangerous_api",),
    execution_mode=ExecutionMode.FILE_PATCH,
    risk=0.5,
)


# --- PLAN-ACTION-04: reward modify schema -----------------------------------

REWARD_MODIFY_SCHEMAS: list[ActionSchema] = [
    ActionSchema(
        kind=ActionKind.REWARD_MODIFY,
        name="modify_item_reward",
        target_tags=("npc", "character", "quest"),
        params=(("item_id", "str"), ("count_delta", "int")),
        constraints=("-100 <= count_delta <= 100",),
        risk=0.3,
    ),
    ActionSchema(
        kind=ActionKind.REWARD_MODIFY,
        name="modify_exp_reward",
        target_tags=("boss", "enemy", "quest"),
        target_numeric_kind="experience",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 10.0",),
        risk=0.25,
    ),
    ActionSchema(
        kind=ActionKind.REWARD_MODIFY,
        name="modify_gold_reward",
        target_tags=("boss", "enemy", "npc"),
        target_numeric_kind="currency",
        params=(("factor", "float"),),
        constraints=("0.1 <= factor <= 10.0",),
        risk=0.25,
    ),
]


class ActionSchemaRegistry:
    """动作 schema 注册表（PLAN-ACTION-01..04 聚合）。"""

    def __init__(self) -> None:
        self._schemas: list[ActionSchema] = []
        self._register_defaults()

    def _register_defaults(self) -> None:
        for s in NUMERIC_SCALE_SCHEMAS:
            self.register(s)
        self.register(SCRIPT_INSERT_SCHEMA)
        for s in REWARD_MODIFY_SCHEMAS:
            self.register(s)

    def register(self, schema: ActionSchema) -> None:
        self._schemas.append(schema)

    def all_schemas(self) -> list[ActionSchema]:
        return list(self._schemas)

    def find_applicable(
        self,
        node_tags: tuple[str, ...],
        numeric_kind: str | None = None,
        kind: ActionKind | None = None,
    ) -> list[ActionSchema]:
        """找出可应用于某节点（按标签/数值类别）的 schema。"""
        result = []
        for schema in self._schemas:
            if kind is not None and schema.kind != kind:
                continue
            # target_tags: 节点需至少有一个匹配标签（或 schema 无标签要求）
            if schema.target_tags:
                if not any(t in node_tags for t in schema.target_tags):
                    continue
            if schema.target_numeric_kind is not None:
                if numeric_kind != schema.target_numeric_kind:
                    continue
            result.append(schema)
        return result


__all__ = [
    "ActionKind",
    "ActionSchema",
    "ActionSchemaRegistry",
    "NUMERIC_SCALE_SCHEMAS",
    "REWARD_MODIFY_SCHEMAS",
    "SCRIPT_INSERT_SCHEMA",
]
