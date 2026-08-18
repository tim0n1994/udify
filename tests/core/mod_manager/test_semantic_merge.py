"""iter4 M3 PR2 — 数值语义合并测试。

覆盖 T3-MODSTACK-REAL 研究落地的白名单（auto）/黑名单（manual）边界：
加法叠加、乘法叠加、SET 取舍、min/max 解析、以及所有必须人工裁决的情况。
"""

from __future__ import annotations

import pytest

from udify.core.mod_manager.real_merge.semantic_merge import (
    NumericEdit,
    SemanticMergeOutcome,
    SemanticOp,
    parse_numeric_edit,
    semantic_merge,
    try_semantic_merge,
)
from udify.core.mod_manager.real_merge.types import ConflictKind, ResolutionStrategy

# --------------------------------------------------------------- parse_numeric_edit


class TestParseNumericEdit:
    """从 patch 表达式推断操作类型。"""

    @pytest.mark.parametrize(
        ("expr", "expected_op"),
        [
            ("200", SemanticOp.SET),
            ("200.5", SemanticOp.SET),
            ("-50", SemanticOp.SET),
            ("0", SemanticOp.SET),
        ],
    )
    def test_parses_set_from_bare_number(self, expr, expected_op):
        edit = parse_numeric_edit(expr, 100.0)
        assert edit is not None
        assert edit.op == expected_op

    @pytest.mark.parametrize(
        ("expr", "expected_value"),
        [
            ("100+=50", 50.0),
            ("100+=50.5", 50.5),
            ("100+=-10", -10.0),
        ],
    )
    def test_parses_add(self, expr, expected_value):
        edit = parse_numeric_edit(expr, 100.0)
        assert edit is not None
        assert edit.op == SemanticOp.ADD
        assert edit.value == expected_value

    @pytest.mark.parametrize(
        ("expr", "expected_value"),
        [
            ("100*=1.5", 1.5),
            ("100*=2", 2.0),
            ("100*=0.5", 0.5),
        ],
    )
    def test_parses_mul(self, expr, expected_value):
        edit = parse_numeric_edit(expr, 100.0)
        assert edit is not None
        assert edit.op == SemanticOp.MUL
        assert edit.value == expected_value

    @pytest.mark.parametrize(
        ("expr", "expected_value"),
        [
            ("min(hp, 999)", 999.0),
            ("max(hp, 100)", 100.0),
            ("min(hp, 50.5)", 50.5),
        ],
    )
    def test_parses_min_max(self, expr, expected_value):
        edit = parse_numeric_edit(expr, 100.0)
        assert edit is not None
        assert edit.op in (SemanticOp.MIN, SemanticOp.MAX)
        assert edit.value == expected_value

    def test_unknown_expression_returns_unknown_op(self):
        edit = parse_numeric_edit("not a number at all", 100.0)
        assert edit is not None
        assert edit.op == SemanticOp.UNKNOWN

    def test_preserves_raw_expression(self):
        edit = parse_numeric_edit("100+=50", 100.0)
        assert edit is not None
        assert edit.raw == "100+=50"


# --------------------------------------------------------------- semantic_merge


class TestSemanticMergeWhitelist:
    """白名单：可自动合并的情况。"""

    def test_both_add_stacks(self):
        """两个 ADD 叠加：base + ours.delta + theirs.delta。"""
        ours = NumericEdit(SemanticOp.ADD, 50.0, "100+=50")
        theirs = NumericEdit(SemanticOp.ADD, 30.0, "100+=30")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 180.0
        assert "叠加" in result.rationale

    def test_both_add_with_negative_stacks(self):
        ours = NumericEdit(SemanticOp.ADD, -20.0, "100+=-20")
        theirs = NumericEdit(SemanticOp.ADD, -10.0, "100+=-10")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 70.0

    def test_both_mul_stacks(self):
        """两个 MUL 叠加：base * ours.delta * theirs.delta。"""
        ours = NumericEdit(SemanticOp.MUL, 1.5, "100*=1.5")
        theirs = NumericEdit(SemanticOp.MUL, 2.0, "100*=2.0")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 300.0

    def test_set_plus_unknown_takes_set(self):
        """一个 SET 一个 UNKNOWN：取 SET 值。"""
        ours = NumericEdit(SemanticOp.SET, 200.0, "200")
        theirs = NumericEdit(SemanticOp.UNKNOWN, 0.0, "???")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 200.0

    def test_unknown_plus_set_takes_set(self):
        ours = NumericEdit(SemanticOp.UNKNOWN, 0.0, "???")
        theirs = NumericEdit(SemanticOp.SET, 200.0, "200")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 200.0

    def test_both_set_same_value(self):
        """两边 SET 相同值：取该值。"""
        ours = NumericEdit(SemanticOp.SET, 200.0, "200")
        theirs = NumericEdit(SemanticOp.SET, 200.0, "200")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is True
        assert result.merged_value == 200.0


class TestSemanticMergeBlacklist:
    """黑名单：必须人工裁决的情况。"""

    def test_both_set_different_values(self):
        ours = NumericEdit(SemanticOp.SET, 200.0, "200")
        theirs = NumericEdit(SemanticOp.SET, 300.0, "300")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is False
        assert result.merged_value is None
        assert "人工裁决" in result.rationale

    def test_both_unknown(self):
        ours = NumericEdit(SemanticOp.UNKNOWN, 0.0, "weird1")
        theirs = NumericEdit(SemanticOp.UNKNOWN, 0.0, "weird2")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is False

    def test_add_and_mul_conflict(self):
        """加法和乘法不可自动合并（语义不可逆）。"""
        ours = NumericEdit(SemanticOp.ADD, 50.0, "100+=50")
        theirs = NumericEdit(SemanticOp.MUL, 1.5, "100*=1.5")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is False

    def test_set_and_add_conflict(self):
        ours = NumericEdit(SemanticOp.SET, 200.0, "200")
        theirs = NumericEdit(SemanticOp.ADD, 50.0, "100+=50")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is False

    def test_add_and_set_conflict(self):
        ours = NumericEdit(SemanticOp.ADD, 50.0, "100+=50")
        theirs = NumericEdit(SemanticOp.SET, 200.0, "200")
        result = semantic_merge(100.0, ours, theirs)
        assert result.auto is False


# --------------------------------------------------------------- try_semantic_merge


class TestTrySemanticMerge:
    """端到端：字符串表达式 -> MergeHunk。"""

    def test_auto_merge_returns_semantic_hunk(self):
        hunk = try_semantic_merge("100", "100+=50", "100+=30", 100.0)
        assert hunk.strategy == ResolutionStrategy.SEMANTIC
        assert hunk.kind == ConflictKind.NONE
        assert hunk.merged == "180.0"

    def test_manual_merge_returns_manual_hunk(self):
        hunk = try_semantic_merge("100", "200", "300", 100.0)
        assert hunk.strategy == ResolutionStrategy.MANUAL
        assert hunk.kind == ConflictKind.SAME_FIELD_DIFFERENT_VALUE
        assert hunk.merged is None
        assert "人工裁决" in hunk.rationale

    def test_unparseable_expression_is_manual(self):
        # parse_numeric_edit returns NumericEdit(UNKNOWN) for unparseable input,
        # never None — so an unparseable + parseable pair routes through
        # semantic_merge as UNKNOWN+ADD, which is correctly blacklisted (manual).
        hunk = try_semantic_merge("100", "not numeric", "100+=50", 100.0)
        assert hunk.strategy == ResolutionStrategy.MANUAL
        assert "人工裁决" in hunk.rationale

    def test_both_unparseable_is_manual(self):
        hunk = try_semantic_merge("100", "garbage1", "garbage2", 100.0)
        assert hunk.strategy == ResolutionStrategy.MANUAL

    def test_both_add_round_trip(self):
        """从字符串表达式到合并值的完整路径。"""
        hunk = try_semantic_merge("100", "100+=25", "100+=75", 100.0)
        assert hunk.strategy == ResolutionStrategy.SEMANTIC
        assert hunk.merged == "200.0"

    def test_both_mul_round_trip(self):
        hunk = try_semantic_merge("100", "100*=2", "100*=3", 100.0)
        assert hunk.strategy == ResolutionStrategy.SEMANTIC
        assert hunk.merged == "600.0"


class TestFrozenDataclassContract:
    """验证核心类型符合项目 frozen + slots 约定。"""

    def test_numeric_edit_is_frozen(self):
        edit = NumericEdit(SemanticOp.SET, 100.0, "100")
        with pytest.raises((AttributeError, TypeError)):
            edit.value = 200.0  # type: ignore[misc]

    def test_semantic_merge_outcome_is_frozen(self):
        outcome = SemanticMergeOutcome(True, 200.0, "test", SemanticOp.SET, SemanticOp.SET)
        with pytest.raises((AttributeError, TypeError)):
            outcome.auto = False  # type: ignore[misc]
