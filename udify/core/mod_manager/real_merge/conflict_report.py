"""
冲突报告与 ModStack 后缀重放（iter4 M3 PR3，T3-MODSTACK-REAL 研究落地）。

两件事：
1. ConflictReport：把 MergeResult 的 hunks 转成前端可渲染的结构化报告（frozen）。
2. suffix_replay：ModStack 移除中间 Mod 时，基于新 base 重算后续 Mod 的合并结果。

设计原则（T3 研究结论）：
- 报告是纯数据，可 JSON 序列化，前端 TS 类型一一对应。
- 后缀重放是「安全重算」：移除 B 后，C 不再基于 B'，而是基于 A' 重新 apply。
  只要 C 的 patch 不变，结果确定性可复现。
- 纯函数，可测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from udify.core.mod_manager.real_merge import MergeResult, merge
from udify.core.mod_manager.real_merge.types import MergeFormat, ResolutionStrategy


class ReportState(StrEnum):
    """报告整体状态。"""

    CLEAN = "clean"  # 全自动合并，无冲突
    HAS_CONFLICTS = "has_conflicts"  # 有 manual 冲突需人工裁决
    EMPTY = "empty"  # 无文件


@dataclass(frozen=True, slots=True)
class ConflictSide:
    """三路合并的一侧内容。"""

    base: str
    ours: str
    theirs: str


@dataclass(frozen=True, slots=True)
class FileConflict:
    """单个文件的冲突/合并结果。"""

    path: str
    hunks: tuple[ConflictSide, ...]
    strategy: ResolutionStrategy
    rationale: str = ""
    merged: str | None = None


@dataclass(frozen=True, slots=True)
class ConflictReport:
    """整个 ModStack 合并的结构化报告（前端可渲染）。"""

    files: tuple[FileConflict, ...]
    state: ReportState
    conflict_count: int
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "files": [
                {
                    "path": f.path,
                    "hunks": [
                        {"base": h.base, "ours": h.ours, "theirs": h.theirs} for h in f.hunks
                    ],
                    "strategy": f.strategy.value,
                    "rationale": f.rationale,
                    "merged": f.merged,
                }
                for f in self.files
            ],
            "state": self.state.value,
            "conflict_count": self.conflict_count,
            "diagnostics": list(self.diagnostics),
        }


def build_report(
    results: dict[str, MergeResult],
) -> ConflictReport:
    """把 per-file MergeResult 聚合成 ConflictReport。

    results: {file_path: MergeResult}
    """
    files: list[FileConflict] = []
    total_conflicts = 0
    diagnostics: list[str] = []
    for path, result in results.items():
        hunks = tuple(ConflictSide(base=h.base, ours=h.ours, theirs=h.theirs) for h in result.hunks)
        # 文件级策略取最严格（任一 hunk manual → 整文件 manual）
        file_strategy = (
            ResolutionStrategy.MANUAL if result.has_conflicts else ResolutionStrategy.AUTO
        )
        files.append(
            FileConflict(
                path=path,
                hunks=hunks,
                strategy=file_strategy,
                rationale="; ".join(h.rationale for h in result.hunks if h.rationale) or "",
                merged=result.merged_text,
            )
        )
        total_conflicts += result.conflict_count
        if result.has_conflicts:
            diagnostics.append(f"{path}: {result.conflict_count} 个冲突需人工裁决")

    if not files:
        state = ReportState.EMPTY
    elif total_conflicts == 0:
        state = ReportState.CLEAN
    else:
        state = ReportState.HAS_CONFLICTS

    return ConflictReport(
        files=tuple(files),
        state=state,
        conflict_count=total_conflicts,
        diagnostics=tuple(diagnostics),
    )


def suffix_replay(
    base: str,
    stack: list[tuple[str, str]],
    remove_idx: int,
    fmt: MergeFormat,
) -> tuple[str, ConflictReport]:
    """ModStack 后缀重放：移除 stack[remove_idx] 后，重算后续合并。

    stack: [(mod_id, content), ...] 按加载顺序。
    remove_idx: 要移除的 Mod 索引。

    返回 (recomputed_content, report)。
    重算策略：跳过 remove_idx，从 base 开始依次 ours=prev, theirs=next 做三路合并。
    对于 3+ Mod 的链式合并，采用「渐进 base」：每步把上一步的合并结果作为新 base。

    这是 PRD 验收标准 #5 的实现。
    """
    if not stack:
        return base, build_report({})
    if remove_idx < 0 or remove_idx >= len(stack):
        raise IndexError(f"remove_idx {remove_idx} 超出 stack 范围 [0, {len(stack)})")

    remaining = [content for i, (_, content) in enumerate(stack) if i != remove_idx]
    if not remaining:
        return base, build_report({})

    # 链式顺序合并：每个剩余 Mod 依次应用到累积结果上。
    # merge(prev, prev, mod) 把 mod 作为单侧变更 apply 到 prev（含 theirs-only 插入），
    # 这样 Mod C 声明的完整内容（含 A 已有的 atk=20 + 自己的 def=5）能正确叠加。
    current = base
    results: dict[str, MergeResult] = {}
    for idx, mod_content in enumerate(remaining):
        result = merge(current, current, mod_content, fmt)
        results[f"replay_step_{idx}"] = result
        if result.merged_text is None:
            break
        current = result.merged_text

    report = build_report(results)
    return current, report
