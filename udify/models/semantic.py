"""
ContentGraph 语义可观测性层（SEM-FIELD-01..03）。

第二轮大迭代的基础设施：给 ContentNode 一个引擎无关、类型安全的语义视图，
让意图接地（cognition）与运行时探针（validation）有可观测锚点。

设计要点（与真实 content_graph.py 对齐）：
- ContentNode 的承载字段是 ``properties: dict[str, Any]``（不是 attributes），
  语义字段作为 ``properties`` 内的约定键 + 一个 frozen 的类型安全访问器。
- 不破坏现有 ContentNode 结构；语义层是叠加而非替换。
- 缺失字段给安全默认值（bool→False、数值→None、str→None），保证调用方永不 KeyError。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from udify.models.content_graph import ContentNode

# 语义属性约定键（引擎适配器感知时填充进 ContentNode.properties）
SEMANTIC_KEYS = {
    "is_boss": bool,
    "is_player": bool,
    "is_enemy": bool,
    "enemy_role": str,
    "display_name": str,
    "hp": int,
    "max_hp": int,
    "attack": int,
    "defense": int,
    "speed": int,
}


@dataclass(frozen=True)
class SemanticView:
    """ContentNode 语义字段的类型安全只读视图。

    所有字段都有安全默认值，缺失字段不抛错。这是意图接地与运行时探针
    定位"Boss vs Hero"这类目标的统一锚点。
    """

    is_boss: bool = False
    is_player: bool = False
    is_enemy: bool = False
    enemy_role: str | None = None
    display_name: str | None = None
    hp: int | None = None
    max_hp: int | None = None
    attack: int | None = None
    defense: int | None = None
    speed: int | None = None

    def is_combatant(self) -> bool:
        """是否是战斗参与者（Boss/敌人/玩家）。"""
        return self.is_boss or self.is_enemy or self.is_player


def get_semantic(node: ContentNode) -> SemanticView:
    """从 ContentNode 提取语义视图。

    读取 ``node.properties`` 内的约定键（兼容驼峰/下划线变体），
    缺失或类型不符的字段给安全默认值。永不抛 KeyError。

    Args:
        node: 内容图谱节点。

    Returns:
        不可变的 SemanticView。
    """
    props: dict[str, object] = dict(getattr(node, "properties", {}) or {})
    # 兼容常见别名
    aliases = {
        "is_boss": ("is_boss", "boss", "IsBoss"),
        "is_player": ("is_player", "is_hero", "player", "hero", "IsPlayer"),
        "is_enemy": ("is_enemy", "enemy", "IsEnemy"),
        "enemy_role": ("enemy_role", "role", "EnemyRole"),
        "display_name": ("display_name", "name", "displayName", "Name"),
        "hp": ("hp", "HP", "hit_points", "Hp"),
        "max_hp": ("max_hp", "maxHp", "MaxHp", "mhp"),
        "attack": ("attack", "atk", "Attack", "Atk"),
        "defense": ("defense", "def", "Defense", "Def"),
        "speed": ("speed", "spd", "Speed", "Spd"),
    }

    def _lookup(canonical: str) -> object | None:
        for key in aliases[canonical]:
            if key in props:
                return props[key]
        return None

    def _as_bool(v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
                "boss",
                "enemy",
                "player",
                "hero",
            }
        return False

    def _as_int(v: object) -> int | None:
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
        return None

    def _as_str(v: object) -> str | None:
        return (
            str(v).strip() or None
            if isinstance(v, str) and v.strip()
            else (str(v) if v is not None else None)
        )

    return SemanticView(
        is_boss=_as_bool(_lookup("is_boss")),
        is_player=_as_bool(_lookup("is_player")),
        is_enemy=_as_bool(_lookup("is_enemy")),
        enemy_role=_as_str(_lookup("enemy_role")),
        display_name=_as_str(_lookup("display_name")),
        hp=_as_int(_lookup("hp")),
        max_hp=_as_int(_lookup("max_hp")),
        attack=_as_int(_lookup("attack")),
        defense=_as_int(_lookup("defense")),
        speed=_as_int(_lookup("speed")),
    )


def set_semantic(node: ContentNode, **fields: object) -> None:
    """把语义字段写回 ContentNode.properties（引擎适配器感知时调用）。

    Args:
        node: 内容图谱节点。
        **fields: 语义字段键值对（必须是 SEMANTIC_KEYS 的子集）。
    """
    invalid = set(fields) - set(SEMANTIC_KEYS)
    if invalid:
        raise KeyError(f"unknown semantic fields: {sorted(invalid)}")
    # ContentNode.properties 可能是默认 factory dict
    props = dict(getattr(node, "properties", {}) or {})
    props.update(fields)
    node.properties = props


__all__ = ["SEMANTIC_KEYS", "SemanticView", "get_semantic", "set_semantic"]
