"""
多 Mod 三路合并（iter4 M3，T3-MODSTACK-REAL 研究落地）。

对叠加的多个 Mod 做 base + ours + theirs 三路合并，按格式分派：
- ini/文本：行级 diff3（difflib.SequenceMatcher）
- json：字段级递归 structured merge（保留键序/缩进）
- 冲突分类：auto（可安全自动合并）/ manual（必须人工裁决）

设计原则（T3 研究结论）：
- 安全边界明确：semantic 合并有白名单（自动）/黑名单（manual）。
- 纯函数，可测试，无副作用。
- 不臆造合并语义——类型冲突、语义不明一律 manual。
"""

from __future__ import annotations

import json

from udify.core.mod_manager.real_merge.json_merge import merge_json_values
from udify.core.mod_manager.real_merge.lua_merge import merge_lua
from udify.core.mod_manager.real_merge.text_merge import merge_ini_lines
from udify.core.mod_manager.real_merge.types import (
    ConflictKind,
    MergeFormat,
    MergeHunk,
    MergeResult,
    ResolutionStrategy,
)


def merge(base: str, ours: str, theirs: str, fmt: MergeFormat) -> MergeResult:
    """三路合并入口，按格式分派。"""
    if fmt in (MergeFormat.INI, MergeFormat.TEXT):
        hunks = merge_ini_lines(base, ours, theirs)
        merged = _assemble(hunks)
        return _result(hunks, merged, fmt)
    if fmt == MergeFormat.JSON:
        return _merge_json_wrapper(base, ours, theirs)
    if fmt == MergeFormat.LUA:
        hunks = merge_lua(base, ours, theirs)
        merged = _assemble(hunks)
        return _result(hunks, merged, fmt)
    hunks = merge_ini_lines(base, ours, theirs)
    merged = _assemble(hunks)
    return _result(hunks, merged, MergeFormat.TEXT)


def _assemble(hunks: list[MergeHunk]) -> str | None:
    parts = []
    for h in hunks:
        if h.strategy == ResolutionStrategy.MANUAL:
            return None
        if h.merged is not None:
            parts.append(h.merged)
    return "".join(parts)


def _result(hunks: list[MergeHunk], merged: str | None, fmt: MergeFormat) -> MergeResult:
    conflict_count = sum(1 for h in hunks if h.strategy == ResolutionStrategy.MANUAL)
    return MergeResult(
        merged_text=merged,
        hunks=tuple(hunks),
        has_conflicts=conflict_count > 0,
        conflict_count=conflict_count,
        format=fmt,
    )


def _merge_json_wrapper(base: str, ours: str, theirs: str) -> MergeResult:
    try:
        base_v = json.loads(base) if base.strip() else {}
        ours_v = json.loads(ours) if ours.strip() else {}
        theirs_v = json.loads(theirs) if theirs.strip() else {}
    except json.JSONDecodeError as e:
        hunk = MergeHunk(
            base=base,
            ours=ours,
            theirs=theirs,
            kind=ConflictKind.STRUCTURAL,
            strategy=ResolutionStrategy.MANUAL,
            rationale=f"JSON 解析失败: {e}",
        )
        return MergeResult(None, (hunk,), True, 1, MergeFormat.JSON)
    merged_v, conflicts = merge_json_values(base_v, ours_v, theirs_v)
    if conflicts:
        hunks = tuple(
            MergeHunk(
                base=str(c["base"]),
                ours=str(c["ours"]),
                theirs=str(c["theirs"]),
                kind=ConflictKind(c.get("kind", ConflictKind.SAME_FIELD_DIFFERENT_VALUE.value)),
                strategy=ResolutionStrategy.MANUAL,
                rationale=c.get("rationale", ""),
            )
            for c in conflicts
        )
        return MergeResult(None, hunks, True, len(conflicts), MergeFormat.JSON)
    merged_text = json.dumps(merged_v, ensure_ascii=False, indent=2)
    hunk = MergeHunk(
        base,
        ours,
        theirs,
        ConflictKind.NONE,
        ResolutionStrategy.AUTO,
        merged_text,
        "JSON 字段级自动合并",
    )
    return MergeResult(merged_text, (hunk,), False, 0, MergeFormat.JSON)


__all__ = [
    "merge",
    "MergeFormat",
    "ConflictKind",
    "ResolutionStrategy",
    "MergeHunk",
    "MergeResult",
]
