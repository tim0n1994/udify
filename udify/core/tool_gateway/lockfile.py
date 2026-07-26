"""
Secure Tool Gateway —— 工具锁文件（TOOL-GW-07，P1）。

对应 ITERATION-PLAN-2026-07.md §4.3 与 §7.3。version + sha256 pin，
防供应链漂移；tool provenance 进 audit。本地用 JSON 存储。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ToolPin:
    """单个工具的版本与完整性锁定。

    Attributes:
        tool_id: 工具标识。
        version: 锁定版本。
        sha256: 工具可执行文件/分发的 sha256（未知为 ``unknown``，但应尽快补齐）。
        source_url: 官方来源 URL。
    """

    tool_id: str
    version: str
    sha256: str = "unknown"
    source_url: str = ""


@dataclass
class ToolLockfile:
    """工具锁文件：所有外部工具的版本 + sha256 pin。"""

    pins: dict[str, ToolPin] = field(default_factory=dict)

    def add(self, pin: ToolPin) -> None:
        self.pins[pin.tool_id] = pin

    def get(self, tool_id: str) -> ToolPin | None:
        return self.pins.get(tool_id)

    def verify(self, tool_id: str, actual_sha256: str) -> bool:
        """校验工具实际 sha256 是否与锁一致。未锁定的工具返回 False。"""
        pin = self.pins.get(tool_id)
        if pin is None or pin.sha256 == "unknown":
            return False
        return pin.sha256 == actual_sha256

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {k: asdict(v) for k, v in self.pins.items()},
                indent=2,
                ensure_ascii=False,
            )
        )

    @classmethod
    def load(cls, path: Path) -> ToolLockfile:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        lf = cls()
        for tool_id, pin_data in data.items():
            lf.pins[tool_id] = ToolPin(**pin_data)
        return lf


def sha256_of_file(path: Path) -> str:
    """计算文件 sha256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = ["ToolLockfile", "ToolPin", "sha256_of_file"]
