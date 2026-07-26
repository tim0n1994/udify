"""
miu2d DSL 命令表（ADAPT-MIU2D-05）。

MODULE-ATTACK-MAP-v3 §5 ADAPT-MIU2D-05：『DSL 命令表 ｜ 218 命令 schema ｜
未知命令标 warning』。

miu2d 的事件脚本（.npc/.txt）使用一套自定义 DSL 命令（如 ShowMessage、GiveItem、
SetSwitch）。本模块定义已知命令 schema，供 patch emitter 校验、planner 识别
"这是奖励/开关/对话"类操作。未知命令标记为 warning（不阻塞，但记录）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DslCommandSchema:
    """单个 DSL 命令的 schema。"""

    name: str
    category: str  # reward / switch / dialogue / flow / system / visual
    params: tuple[str, ...]  # 参数名
    risk: float = 0.1  # 0-1
    reversible: bool = True


# miu2d 常见 DSL 命令（精选核心，覆盖奖励/开关/对话/流程/系统）
# 真实 miu2d 有更多，这里建立可扩展的 schema 注册表结构。
_KNOWN_COMMANDS: dict[str, DslCommandSchema] = {
    # 对话
    "ShowMessage": DslCommandSchema("ShowMessage", "dialogue", ("text",)),
    "ShowChoice": DslCommandSchema("ShowChoice", "dialogue", ("choices",)),
    "ShowMessageWithName": DslCommandSchema("ShowMessageWithName", "dialogue", ("name", "text")),
    # 奖励
    "GiveItem": DslCommandSchema("GiveItem", "reward", ("item_id", "count"), risk=0.2),
    "GiveGold": DslCommandSchema("GiveGold", "reward", ("amount",), risk=0.2),
    "GiveExp": DslCommandSchema("GiveExp", "reward", ("amount",), risk=0.2),
    "GiveSkill": DslCommandSchema("GiveSkill", "reward", ("skill_id",), risk=0.3),
    "RemoveItem": DslCommandSchema("RemoveItem", "reward", ("item_id", "count"), risk=0.3),
    # 开关/变量
    "SetSwitch": DslCommandSchema("SetSwitch", "switch", ("switch_id", "value")),
    "SetVariable": DslCommandSchema("SetVariable", "switch", ("var_id", "value")),
    "GetSwitch": DslCommandSchema("GetSwitch", "switch", ("switch_id",)),
    # 流程控制
    "If": DslCommandSchema("If", "flow", ("condition",)),
    "Else": DslCommandSchema("Else", "flow", ()),
    "Wait": DslCommandSchema("Wait", "flow", ("frames",)),
    "Branch": DslCommandSchema("Branch", "flow", ("label",)),
    "Goto": DslCommandSchema("Goto", "flow", ("label",), risk=0.4),
    "CallEvent": DslCommandSchema("CallEvent", "flow", ("event_id",), risk=0.3),
    # 系统
    "ChangeHP": DslCommandSchema("ChangeHP", "system", ("amount",), risk=0.5),
    "ChangeMP": DslCommandSchema("ChangeMP", "system", ("amount",), risk=0.5),
    "ChangeLevel": DslCommandSchema("ChangeLevel", "system", ("levels",), risk=0.6),
    "Teleport": DslCommandSchema("Teleport", "system", ("map_id", "x", "y"), risk=0.5),
    "PlaySound": DslCommandSchema("PlaySound", "system", ("sound_id",)),
    "PlayBGM": DslCommandSchema("PlayBGM", "system", ("bgm_id",)),
    "SaveGame": DslCommandSchema("SaveGame", "system", (), risk=0.4),
    "LoadGame": DslCommandSchema("LoadGame", "system", (), risk=0.6, reversible=False),
    "GameOver": DslCommandSchema("GameOver", "system", (), risk=0.8, reversible=False),
    # 视觉
    "ShowPicture": DslCommandSchema("ShowPicture", "visual", ("picture_id", "x", "y")),
    "HidePicture": DslCommandSchema("HidePicture", "visual", ("picture_id",)),
    "ScreenFade": DslCommandSchema("ScreenFade", "visual", ("duration", "color")),
}


class DslCommandRegistry:
    """DSL 命令注册表（ADAPT-MIU2D-05）。"""

    def __init__(self) -> None:
        self._commands: dict[str, DslCommandSchema] = dict(_KNOWN_COMMANDS)

    def get(self, name: str) -> DslCommandSchema | None:
        """查询命令 schema；未知返回 None。"""
        return self._commands.get(name)

    def is_known(self, name: str) -> bool:
        return name in self._commands

    def category(self, name: str) -> str | None:
        schema = self.get(name)
        return schema.category if schema else None

    def validate(self, name: str, args: list[Any]) -> tuple[bool, str]:
        """校验命令调用。未知命令 → warning（允许但记录）。"""
        schema = self.get(name)
        if schema is None:
            return (True, f"unknown command '{name}' (warning)")
        if len(args) < len(schema.params):
            return (
                False,
                f"{name} expects >={len(schema.params)} args, got {len(args)}",
            )
        return (True, "ok")

    def all_commands(self) -> dict[str, DslCommandSchema]:
        return dict(self._commands)

    def register(self, schema: DslCommandSchema) -> None:
        self._commands[schema.name] = schema


__all__ = ["DslCommandRegistry", "DslCommandSchema"]
