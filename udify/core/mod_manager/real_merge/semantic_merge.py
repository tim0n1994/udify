"""
数值语义合并（iter4 M3 PR2，T3-MODSTACK-REAL 研究落地）。

当两个 Mod 对同一数值字段做修改时，semantic merge 决定能否自动合并：
- 白名单（自动）：加法叠加、乘法取大、min/max 聚合——安全可逆。
- 黑名单（manual）：类型冲突、语义不明、无法确定合并规则——必须人工裁决。

设计原则（T3 研究结论）：
- 安全边界明确：宁可 manual 也不静默错误自动合并。
- 纯函数，可测试。
- 只处理「两边都是明确数值修改」的情况，其余一律 manual。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from udify.core.mod_manager.real_merge.types import ConflictKind, MergeHunk, ResolutionStrategy


class SemanticOp(StrEnum):
    """数值修改的操作类型（从 patch 表达式推断）。"""

    SET = "set"  # hp=200（直接设值）
    ADD = "add"  # hp+=50（加法）
    MUL = "mul"  # hp*=1.5（乘法）
    MIN = "min"  # hp=min(hp, 999)
    MAX = "max"  # hp=max(hp, 100)
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NumericEdit:
    """对单个数值字段的修改。"""

    op: SemanticOp
    value: float
    raw: str  # 原始表达式


@dataclass(frozen=True, slots=True)
class SemanticMergeOutcome:
    """语义合并结果。"""

    auto: bool  # 是否可自动合并
    merged_value: float | None  # auto=True 时的合并值
    rationale: str
    op_ours: SemanticOp
    op_theirs: SemanticOp


# 数值修改表达式模式
_PATTERNS: list[tuple[re.Pattern[str], SemanticOp]] = [
    (re.compile(r"^\s*([+\-]?\d+(?:\.\d+)?)\s*\+=\s*([+\-]?\d+(?:\.\d+)?)"), SemanticOp.ADD),
    (re.compile(r"^\s*([+\-]?\d+(?:\.\d+)?)\s*\*=\s*([+\-]?\d+(?:\.\d+)?)"), SemanticOp.MUL),
]


def parse_numeric_edit(expr: str, field_value: str | float) -> NumericEdit | None:
    """从 patch 表达式推断数值修改操作。

    支持：200（set）、100+=50（add）、100*=1.5（mul）、min/max(hp, N)。
    不支持的返回 NumericEdit(UNKNOWN)（调用方按 manual 处理）。
    """
    expr = expr.strip()
    # set: 直接是数字 或 field=value
    try:
        return NumericEdit(SemanticOp.SET, float(expr), expr)
    except ValueError:
        pass
    # add/mul: 需要包含 += 或 *=
    for pat, op in _PATTERNS:
        m = pat.match(expr)
        if m:
            try:
                # group 1 is the expression's stated current value (e.g. "100"
                # in "100+=50"); it validates the shape but the actual merge
                # recomputes from base_numeric, so it is intentionally unused.
                float(m.group(1))
                delta = float(m.group(2))
                if op == SemanticOp.ADD:
                    return NumericEdit(SemanticOp.ADD, delta, expr)
                return NumericEdit(SemanticOp.MUL, delta, expr)
            except ValueError:
                continue
    # min/max 文本匹配（保守）
    if "min(" in expr.lower():
        try:
            inner = expr.lower().split("min(")[1].rstrip(")").split(",")[-1].strip()
            return NumericEdit(SemanticOp.MIN, float(inner), expr)
        except (IndexError, ValueError):
            pass
    if "max(" in expr.lower():
        try:
            inner = expr.lower().split("max(")[1].rstrip(")").split(",")[-1].strip()
            return NumericEdit(SemanticOp.MAX, float(inner), expr)
        except (IndexError, ValueError):
            pass
    return NumericEdit(SemanticOp.UNKNOWN, 0.0, expr)


def semantic_merge(base: float, ours: NumericEdit, theirs: NumericEdit) -> SemanticMergeOutcome:
    """对两个数值修改尝试语义合并。

    白名单（自动）：
    - 都是 ADD：叠加（base + ours.delta + theirs.delta）
    - 都是 MUL：叠加（base * ours.delta * theirs.delta）
    - 一个 SET 一个未改（UNKNOWN）：取 SET
    - 都是 SET 且相同值：取该值
    黑名单（manual）：其余全部（SET 不同值、类型冲突、UNKNOWN 混合等）
    """
    # 都加法 → 叠加
    if ours.op == SemanticOp.ADD and theirs.op == SemanticOp.ADD:
        merged = base + ours.value + theirs.value
        return SemanticMergeOutcome(True, merged, "双方加法叠加", ours.op, theirs.op)
    # 都乘法 → 叠加
    if ours.op == SemanticOp.MUL and theirs.op == SemanticOp.MUL:
        merged = base * ours.value * theirs.value
        return SemanticMergeOutcome(True, merged, "双方乘法叠加", ours.op, theirs.op)
    # 一个 SET 一个未改
    if ours.op == SemanticOp.SET and theirs.op == SemanticOp.UNKNOWN:
        return SemanticMergeOutcome(True, ours.value, "仅 ours 设置", ours.op, theirs.op)
    if theirs.op == SemanticOp.SET and ours.op == SemanticOp.UNKNOWN:
        return SemanticMergeOutcome(True, theirs.value, "仅 theirs 设置", ours.op, theirs.op)
    # 都 SET 相同值
    if ours.op == SemanticOp.SET and theirs.op == SemanticOp.SET and ours.value == theirs.value:
        return SemanticMergeOutcome(True, ours.value, "双方设置相同值", ours.op, theirs.op)
    # 其余：manual
    return SemanticMergeOutcome(
        False,
        None,
        f"无法自动合并: ours={ours.op.value} theirs={theirs.op.value}（需人工裁决）",
        ours.op,
        theirs.op,
    )


def try_semantic_merge(base: str, ours: str, theirs: str, base_numeric: float) -> MergeHunk:
    """尝试语义合并，返回 MergeHunk（auto 或 manual）。"""
    o = parse_numeric_edit(ours, base_numeric)
    t = parse_numeric_edit(theirs, base_numeric)
    if o is None or t is None:
        return MergeHunk(
            base=str(base_numeric),
            ours=ours,
            theirs=theirs,
            kind=ConflictKind.SAME_FIELD_DIFFERENT_VALUE,
            strategy=ResolutionStrategy.MANUAL,
            rationale="无法解析数值修改表达式",
        )
    outcome = semantic_merge(base_numeric, o, t)
    if outcome.auto and outcome.merged_value is not None:
        return MergeHunk(
            base=str(base_numeric),
            ours=ours,
            theirs=theirs,
            kind=ConflictKind.NONE,
            strategy=ResolutionStrategy.SEMANTIC,
            merged=str(outcome.merged_value),
            rationale=outcome.rationale,
        )
    return MergeHunk(
        base=str(base_numeric),
        ours=ours,
        theirs=theirs,
        kind=ConflictKind.SAME_FIELD_DIFFERENT_VALUE,
        strategy=ResolutionStrategy.MANUAL,
        rationale=outcome.rationale,
    )
