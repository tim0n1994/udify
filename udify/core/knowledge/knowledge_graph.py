"""
Udify Knowledge - Game Knowledge Graph

游戏知识图谱：RPG 通用知识 + miu2d 特有知识。
用于验证 AI 生成的修改是否合理。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class KnowledgeRule:
    """知识规则"""

    rule_id: str
    category: str
    description: str
    severity: str = "warning"  # info, warning, error, critical
    condition: str | None = None
    recommended_range: tuple | None = None


@dataclass
class KnowledgeWarning:
    """知识警告"""

    level: str
    message: str
    rule_id: str | None = None
    operation_type: str | None = None
    target_id: str | None = None


class GameKnowledgeGraph:
    """
    游戏知识图谱

    包含:
    1. RPG 通用平衡规则
    2. 机制关系知识
    3. 常见模式
    4. 危险模式
    5. miu2d 特有知识
    """

    def __init__(self) -> None:
        self._rules: dict[str, KnowledgeRule] = {}
        self._mechanic_relationships: list[dict[str, Any]] = []
        self._common_patterns: dict[str, dict[str, Any]] = {}
        self._dangerous_patterns: list[dict[str, Any]] = []
        self._miu2d_knowledge: dict[str, Any] = {}

        self._init_rpg_knowledge()
        self._init_miu2d_knowledge()

    def _init_rpg_knowledge(self) -> None:
        """初始化 RPG 通用知识"""
        # 平衡规则
        balance_rules = [
            ("boss_hp_ratio", "BOSS 生命值通常是普通怪物的 5-10 倍", "info", (5.0, 10.0)),
            ("exp_curve", "每级所需经验通常呈指数增长", "info", None),
            ("drop_rate_cap", "掉落率不应超过 100%，也不应低于 0.01%", "error", (0.0001, 1.0)),
            ("stat_scaling", "属性增长不应超过基础值的 1000 倍", "warning", (0.1, 1000.0)),
            ("hp_reasonable", "角色生命值应在 1-999999 范围内", "error", (1, 999999)),
            ("mp_reasonable", "角色法力值应在 0-999999 范围内", "error", (0, 999999)),
            ("stat_positive", "主要属性不应为负数", "error", (0, None)),
            ("price_positive", "物品价格不应为负数", "error", (0, None)),
            ("level_range", "地图适合等级范围应在 1-99 之间", "warning", (1, 99)),
        ]

        for rule_id, desc, severity, range_val in balance_rules:
            self._rules[rule_id] = KnowledgeRule(
                rule_id=rule_id,
                category="balance",
                description=desc,
                severity=severity,
                recommended_range=range_val,
            )

        # 机制关系
        self._mechanic_relationships = [
            {"cause": "increase_boss_hp", "effect": "increase_exp_reward", "strength": 0.8},
            {"cause": "increase_drop_rate", "effect": "decrease_item_value", "strength": 0.6},
            {
                "cause": "increase_player_speed",
                "effect": "decrease_game_difficulty",
                "strength": 0.7,
            },
            {"cause": "increase_enemy_count", "effect": "increase_exp_per_hour", "strength": 0.9},
            {"cause": "decrease_cooldown", "effect": "increase_dps", "strength": 0.8},
        ]

        # 常见模式
        self._common_patterns = {
            "hard_mode": {
                "description": "困难模式：敌人血量×2，攻击力×1.5，经验×1.2",
                "modifications": [
                    {"target": "enemy", "property": "hp", "factor": 2.0},
                    {"target": "enemy", "property": "attack", "factor": 1.5},
                    {"target": "player", "property": "exp_gain", "factor": 1.2},
                ],
            },
            "easy_mode": {
                "description": "简单模式：玩家血量×2，敌人攻击力×0.7",
                "modifications": [
                    {"target": "player", "property": "hp", "factor": 2.0},
                    {"target": "enemy", "property": "attack", "factor": 0.7},
                ],
            },
            "loot_fiesta": {
                "description": "掉落狂欢：掉落率×3，稀有物品出现率×2",
                "modifications": [
                    {"target": "drop", "property": "rate", "factor": 3.0},
                    {"target": "rare_drop", "property": "rate", "factor": 2.0},
                ],
            },
            "xp_boost": {
                "description": "经验加成：经验获取×2，升级所需经验×0.8",
                "modifications": [
                    {"target": "player", "property": "exp_gain", "factor": 2.0},
                    {"target": "level", "property": "exp_required", "factor": 0.8},
                ],
            },
        }

        # 危险模式
        self._dangerous_patterns = [
            {
                "pattern": "set_hp_to_999999",
                "risk": "破坏游戏平衡，导致无敌",
                "severity": "critical",
            },
            {
                "pattern": "delete_all_enemies",
                "risk": "删除所有敌人导致无法通关",
                "severity": "critical",
            },
            {"pattern": "set_exp_to_zero", "risk": "无法升级导致游戏卡住", "severity": "critical"},
            {"pattern": "set_all_stats_to_max", "risk": "破坏成长曲线", "severity": "high"},
            {"pattern": "remove_all_obstacles", "risk": "地图可 walkthrough", "severity": "high"},
            {"pattern": "infinite_gold", "risk": "破坏经济系统", "severity": "high"},
        ]

    def _init_miu2d_knowledge(self) -> None:
        """初始化 miu2d 特有知识"""
        self._miu2d_knowledge = {
            "magic_combos": [
                {"combo": "fire + ice", "result": "steam_blast", "power": 1.5},
                {"combo": "lightning + water", "result": "chain_lightning", "power": 2.0},
                {"combo": "fire + wind", "result": "firestorm", "power": 1.8},
            ],
            "npc_archetypes": [
                {
                    "archetype": "tutorial_mentor",
                    "typical_stats": {"hp": 100, "friendly": True, "level": 1},
                },
                {"archetype": "first_boss", "typical_stats": {"hp": 500, "level": 5, "attack": 30}},
                {"archetype": "mid_boss", "typical_stats": {"hp": 2000, "level": 20, "attack": 80}},
                {
                    "archetype": "final_boss",
                    "typical_stats": {"hp": 10000, "level": 50, "attack": 200},
                },
                {"archetype": "merchant", "typical_stats": {"hp": 50, "friendly": True}},
            ],
            "map_regions": [
                {
                    "region": "starter_village",
                    "level_range": (1, 5),
                    "enemy_types": ["slime", "wolf", "rabbit"],
                },
                {
                    "region": "dark_forest",
                    "level_range": (10, 20),
                    "enemy_types": ["skeleton", "ghost", "spider"],
                },
                {
                    "region": "volcano",
                    "level_range": (25, 35),
                    "enemy_types": ["fire_elemental", "demon"],
                },
                {
                    "region": "ice_castle",
                    "level_range": (40, 50),
                    "enemy_types": ["ice_golem", "frost_dragon"],
                },
            ],
            "move_kinds": [
                "LineMove",
                "CircleMove",
                "SpiralMove",
                "SectorMove",
                "HeartMove",
                "FollowEnemy",
                "Throw",
                "Transport",
                "Summon",
                "TimeStop",
                "VMove",
            ],
            "special_kinds": [
                "freeze",
                "poison",
                "petrify",
                "invisibility",
                "heal",
                "buff",
                "transform",
                "remove_debuff",
            ],
        }

    def validate_mod_against_knowledge(
        self, operations: list[dict[str, Any]]
    ) -> list[KnowledgeWarning]:
        """根据知识图谱验证修改的合理性"""
        warnings = []

        for op in operations:
            # 检查危险模式
            for dangerous in self._dangerous_patterns:
                if dangerous["pattern"] in str(op):
                    warnings.append(
                        KnowledgeWarning(
                            level="critical",
                            message=f"检测到危险模式: {dangerous['risk']}",
                            rule_id="dangerous_pattern",
                            operation_type=op.get("op_type"),
                        )
                    )

            # 检查数值规则
            if op.get("op_type") in ["MODIFY_INI", "MODIFY_PROPERTY"]:
                key = op.get("payload", {}).get("key", "")
                new_value = op.get("payload", {}).get("value")

                # 检查特定规则
                rule_checks = [
                    (
                        "MaxLife",
                        "hp_reasonable",
                        lambda v: isinstance(v, (int, float)) and (v < 1 or v > 999999),
                    ),
                    (
                        "MaxMana",
                        "mp_reasonable",
                        lambda v: isinstance(v, (int, float)) and (v < 0 or v > 999999),
                    ),
                    ("Strength", "stat_positive", lambda v: isinstance(v, (int, float)) and v < 0),
                    ("Dexterity", "stat_positive", lambda v: isinstance(v, (int, float)) and v < 0),
                    ("price", "price_positive", lambda v: isinstance(v, (int, float)) and v < 0),
                ]

                for check_key, rule_id, check_func in rule_checks:
                    if check_key.lower() in key.lower() and check_func(new_value):
                        rule = self._rules.get(rule_id)
                        if rule:
                            warnings.append(
                                KnowledgeWarning(
                                    level=rule.severity,
                                    message=f"{rule.description}: {key} = {new_value}",
                                    rule_id=rule_id,
                                    operation_type="MODIFY_INI",
                                    target_id=op.get("target_id"),
                                )
                            )

        return warnings

    def get_recommended_pattern(self, intent: str) -> dict[str, Any] | None:
        """根据意图推荐成功模式"""
        intent_lower = intent.lower()

        # 关键词匹配
        pattern_keywords = {
            "hard_mode": ["困难", "hard", "难", "difficult", "挑战", "challenge"],
            "easy_mode": ["简单", "easy", "简单模式", "休闲", "casual"],
            "loot_fiesta": ["掉落", "loot", "掉率", "drop", "装备", "item"],
            "xp_boost": ["经验", "exp", "升级", "level", "快速升级"],
        }

        for pattern_name, keywords in pattern_keywords.items():
            if any(kw in intent_lower for kw in keywords):
                return self._common_patterns.get(pattern_name)

        return None

    def get_related_mechanics(self, action: str) -> list[dict[str, Any]]:
        """获取与某个机制相关的其他机制"""
        results = []
        for rel in self._mechanic_relationships:
            if rel["cause"] == action or rel["effect"] == action:
                results.append(rel)
        return results

    def get_npc_archetype(self, name: str) -> dict[str, Any] | None:
        """获取 NPC 原型"""
        name_lower = name.lower()
        for archetype in self._miu2d_knowledge.get("npc_archetypes", []):
            if archetype["archetype"] in name_lower:
                return archetype
        return None

    def get_map_region(self, map_name: str) -> dict[str, Any] | None:
        """获取地图区域信息"""
        name_lower = map_name.lower()
        for region in self._miu2d_knowledge.get("map_regions", []):
            if region["region"] in name_lower:
                return region
        return None

    def is_valid_magic_combo(self, move_kind: str, special_kind: str) -> bool:
        """检查是否为有效的技能组合"""
        valid_moves = self._miu2d_knowledge.get("move_kinds", [])
        valid_specials = self._miu2d_knowledge.get("special_kinds", [])
        return move_kind in valid_moves and special_kind in valid_specials

    def get_knowledge_summary(self) -> dict[str, Any]:
        """获取知识摘要"""
        return {
            "rule_count": len(self._rules),
            "relationship_count": len(self._mechanic_relationships),
            "pattern_count": len(self._common_patterns),
            "dangerous_pattern_count": len(self._dangerous_patterns),
            "npc_archetype_count": len(self._miu2d_knowledge.get("npc_archetypes", [])),
            "map_region_count": len(self._miu2d_knowledge.get("map_regions", [])),
        }
