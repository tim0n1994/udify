"""三路合并的共享类型（独立模块，避免循环导入）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MergeFormat(StrEnum):
    INI = "ini"
    JSON = "json"
    TEXT = "text"
    LUA = "lua"
    UNKNOWN = "unknown"


class ConflictKind(StrEnum):
    NONE = "none"
    SAME_FIELD_DIFFERENT_VALUE = "same_field_different_value"
    TYPE_MISMATCH = "type_mismatch"
    STRUCTURAL = "structural"


class ResolutionStrategy(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class MergeHunk:
    """单个合并单元。"""

    base: str
    ours: str
    theirs: str
    kind: ConflictKind
    strategy: ResolutionStrategy
    merged: str | None = None
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class MergeResult:
    """三路合并结果。"""

    merged_text: str | None
    hunks: tuple[MergeHunk, ...]
    has_conflicts: bool
    conflict_count: int = 0
    format: MergeFormat = MergeFormat.UNKNOWN

    @property
    def fully_auto_merged(self) -> bool:
        return self.merged_text is not None and not self.has_conflicts
