"""意图评测集（iter3 N4 / S5-BENCH）。

>=30 个意图 case，含圈外（非 miu2d）。每个标注期望 IntentType + 期望目标节点类型
+ 是否应误伤。用于 heuristic vs target_resolver vs LLM 的离线 A/B 对照。
"""

from __future__ import annotations

from dataclasses import dataclass

from udify.core.cognition.intent import IntentType


@dataclass
class IntentCase:
    """一个意图评测 case。"""

    case_id: str
    text: str
    expect_type: IntentType
    expect_target_keyword: str  # 期望命中的目标描述关键词
    should_misfire: bool = False  # 期望是否产生误伤（True=正确行为是不误伤）
    domain: str = "miu2d"  # miu2d / outsider（圈外）
    difficulty: str = "easy"  # easy/medium/hard
    notes: str = ""


# 30 个 case：miu2d 内 + 圈外，含歧义/负向偏好
CASES: list[IntentCase] = [
    # --- miu2d 基础（easy）---
    IntentCase("c01", "把第一个 Boss 的血量翻倍", IntentType.DIFFICULTY_ADJUSTMENT, "boss"),
    IntentCase("c02", "降低哥布林的攻击力", IntentType.DIFFICULTY_ADJUSTMENT, "enemy"),
    IntentCase("c03", "增加主角的最大生命值", IntentType.DIFFICULTY_ADJUSTMENT, "player"),
    IntentCase("c04", "新增一把剑", IntentType.CONTENT_EXPANSION, "item"),
    IntentCase("c05", "添加一个新 NPC", IntentType.CONTENT_EXPANSION, "npc"),
    # --- miu2d 歧义/消歧（medium）---
    IntentCase(
        "c06",
        "让 Boss 更难但不碰主角",
        IntentType.DIFFICULTY_ADJUSTMENT,
        "boss",
        should_misfire=True,
    ),
    IntentCase("c07", "所有敌人的血量加 100", IntentType.DIFFICULTY_ADJUSTMENT, "enemy"),
    IntentCase("c08", "把最终 Boss 的防御提高", IntentType.DIFFICULTY_ADJUSTMENT, "boss"),
    IntentCase(
        "c09",
        "不要只翻倍血量，让 Boss 更狡猾",
        IntentType.DIFFICULTY_ADJUSTMENT,
        "boss",
        should_misfire=True,
    ),
    IntentCase("c10", "强化第一个 Boss，弱化第二个", IntentType.DIFFICULTY_ADJUSTMENT, "boss"),
    # --- miu2d 机制/叙事（medium）---
    IntentCase("c11", "修改暴击率计算", IntentType.GAMEPLAY_MECHANIC, "mechanic"),
    IntentCase("c12", "改掉死亡惩罚机制", IntentType.GAMEPLAY_MECHANIC, "mechanic"),
    IntentCase(
        "c13", "让游戏更像魂系", IntentType.DIFFICULTY_ADJUSTMENT, "boss", difficulty="hard"
    ),
    IntentCase("c14", "增加一个支线任务", IntentType.CONTENT_EXPANSION, "quest"),
    IntentCase("c15", "修改开场剧情对话", IntentType.NARRATIVE_CHANGE, "dialogue"),
    # --- miu2d 视觉/平衡（medium）---
    IntentCase("c16", "把 UI 改成暗色", IntentType.VISUAL_STYLE, "ui"),
    IntentCase("c17", "调整经济平衡，金币掉落减半", IntentType.GAMEPLAY_MECHANIC, "mechanic"),
    IntentCase("c18", "给 Boss 加一个新技能", IntentType.CONTENT_EXPANSION, "boss"),
    IntentCase("c19", "缩短关卡长度", IntentType.GAMEPLAY_MECHANIC, "level"),
    IntentCase("c20", "让某个 NPC 卖新东西", IntentType.CONTENT_EXPANSION, "npc"),
    # --- 圈外（outsider，非 miu2d）---
    IntentCase(
        "o01",
        "把 RPG Maker 游戏里 1 号敌人的 HP 改成 999",
        IntentType.DIFFICULTY_ADJUSTMENT,
        "enemy",
        domain="outsider",
    ),
    IntentCase(
        "o02",
        "在 Unity 游戏里给玩家加双跳",
        IntentType.GAMEPLAY_MECHANIC,
        "player",
        domain="outsider",
    ),
    IntentCase(
        "o03", "修改 Godot 游戏的重力", IntentType.GAMEPLAY_MECHANIC, "mechanic", domain="outsider"
    ),
    IntentCase(
        "o04", "给 Minecraft 加一个新方块", IntentType.CONTENT_EXPANSION, "item", domain="outsider"
    ),
    IntentCase(
        "o05",
        "让 Skyrim 的龙更强但别太离谱",
        IntentType.DIFFICULTY_ADJUSTMENT,
        "boss",
        domain="outsider",
        should_misfire=True,
    ),
    IntentCase(
        "o06", "修改 Pokemon 的遇敌率", IntentType.GAMEPLAY_MECHANIC, "mechanic", domain="outsider"
    ),
    IntentCase(
        "o07",
        "在 Stardew Valley 加一个新作物",
        IntentType.CONTENT_EXPANSION,
        "item",
        domain="outsider",
    ),
    IntentCase(
        "o08",
        "让 Dark Souls 的 bosses 整体变难",
        IntentType.DIFFICULTY_ADJUSTMENT,
        "boss",
        domain="outsider",
    ),
    IntentCase(
        "o09",
        "修改 Terraria 的 boss 召唤条件",
        IntentType.GAMEPLAY_MECHANIC,
        "mechanic",
        domain="outsider",
    ),
    IntentCase(
        "o10",
        "给 WoW 的某个副本加机制",
        IntentType.GAMEPLAY_MECHANIC,
        "mechanic",
        domain="outsider",
        difficulty="hard",
    ),
]


def load_cases(domain: str | None = None) -> list[IntentCase]:
    """加载评测 case，可按域过滤。"""
    if domain is None:
        return list(CASES)
    return [c for c in CASES if c.domain == domain]


__all__ = ["CASES", "IntentCase", "load_cases"]
