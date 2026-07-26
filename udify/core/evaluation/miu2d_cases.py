"""
miu2d 首批 10 个 golden cases（BENCH-02）。

MODULE-ATTACK-MAP-v3 §15：
1. 初始角色 HP 修改
2. Boss 难度提升但 HP 不超过 1.35 倍
3. NPC 对话奖励技能
4. 物品掉落率提高
5. 治疗道具削弱
6. 新增商店物品
7. 地图入口到出口可达性保持
8. 禁止危险 Lua API
9. 多 Mod 同属性冲突
10. Patch 回滚后 graph checksum 一致
"""

from __future__ import annotations

from udify.core.evaluation.benchmark_runner import BenchmarkCase
from udify.core.evaluation.eval_v3 import GoldenCase

# 共用的 miu2d 游戏夹具
_BASE_FIXTURE = {
    "characters.ini": (
        "[Boss]\nMaxLife=500\nAttack=50\nDefense=20\nDropRate=0.1\n"
        "[Hero]\nMaxLife=100\nAttack=15\nDefense=10\n"
    ),
    "items.ini": (
        "[Potion]\nType=heal\nValue=50\nPrice=20\n[Sword]\nType=weapon\nAttack=20\nPrice=100\n"
    ),
}


def _case(
    case_id: str,
    intent: str,
    expected=None,
    forbidden=None,
    constraints=None,
    fixture=None,
) -> BenchmarkCase:
    return BenchmarkCase(
        case=GoldenCase(
            case_id=case_id,
            intent=intent,
            expected_patterns=expected or [],
            forbidden_patterns=forbidden or [],
            hard_constraints=constraints or [],
        ),
        game_fixture=fixture or dict(_BASE_FIXTURE),
    )


def get_miu2d_golden_cases() -> list[BenchmarkCase]:
    """返回 10 个首批 golden cases（BENCH-02）。"""
    return [
        # 1. 初始角色 HP 修改
        _case(
            "01-hp-modify",
            "让Boss血量翻倍",
            expected=[{"key": "MaxLife"}],
            constraints=["factor <= 5.0"],
        ),
        # 2. Boss 难度提升但 HP 不超过 1.35 倍
        _case(
            "02-boss-difficulty-capped",
            "让Boss更难，血量1.3倍",
            expected=[{"key": "MaxLife"}],
            constraints=["factor <= 1.35"],
        ),
        # 3. NPC 对话奖励技能（DSL 奖励类）
        _case(
            "03-npc-skill-reward",
            "给NPC对话增加技能奖励",
            expected=[{"command": "GiveSkill"}],
        ),
        # 4. 物品掉落率提高
        _case(
            "04-drop-rate-up",
            "提高Boss掉落率",
            expected=[{"key": "DropRate"}],
            constraints=["factor <= 10.0"],
        ),
        # 5. 治疗道具削弱
        _case(
            "05-potion-nerf",
            "削弱治疗道具效果",
            expected=[{"key": "Value"}],
            constraints=["factor >= 0.1"],
        ),
        # 6. 新增商店物品
        _case(
            "06-add-shop-item",
            "新增一个商店物品",
            expected=[{"op": "ADD"}],
        ),
        # 7. 地图可达性保持（静态：不删除关键节点）
        _case(
            "07-map-reachability",
            "调整难度但保持地图可达性",
            forbidden=[{"op": "REMOVE_NODE"}],
        ),
        # 8. 禁止危险 Lua API
        _case(
            "08-no-dangerous-lua",
            "给Boss加一个脚本效果",
            forbidden=[{"key": "os.execute"}, {"key": "loadstring"}],
        ),
        # 9. 多 Mod 同属性冲突（patch 不应含对同一属性的多重矛盾修改）
        _case(
            "09-no-conflicting-edits",
            "让Boss血量翻倍",
            constraints=["factor <= 5.0"],
        ),
        # 10. Patch 回滚后 checksum 一致（由 benchmark test 单独验证）
        _case(
            "10-rollback-checksum",
            "让Boss血量翻倍",
            expected=[{"key": "MaxLife"}],
            constraints=["factor <= 5.0"],
        ),
    ]


__all__ = ["get_miu2d_golden_cases"]
