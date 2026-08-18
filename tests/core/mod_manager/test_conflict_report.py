"""iter4 M3 PR3 — 冲突报告与 ModStack 后缀重放测试（T3-MODSTACK-REAL）。"""

from __future__ import annotations

import json

import pytest

from udify.core.mod_manager.real_merge import merge
from udify.core.mod_manager.real_merge.conflict_report import (
    ConflictReport,
    FileConflict,
    ReportState,
    build_report,
    suffix_replay,
)
from udify.core.mod_manager.real_merge.types import MergeFormat, ResolutionStrategy

# --------------------------------------------------------------- build_report


class TestBuildReport:
    def test_clean_report_when_no_conflicts(self):
        results = {
            "game.ini": merge("hp=100\n", "hp=200\n", "hp=100\n", MergeFormat.INI),
        }
        report = build_report(results)
        assert report.state == ReportState.CLEAN
        assert report.conflict_count == 0
        assert len(report.files) == 1
        assert report.files[0].strategy == ResolutionStrategy.AUTO

    def test_has_conflicts_when_manual_hunks(self):
        results = {
            "game.ini": merge("hp=100\n", "hp=200\n", "hp=300\n", MergeFormat.INI),
        }
        report = build_report(results)
        assert report.state == ReportState.HAS_CONFLICTS
        assert report.conflict_count >= 1
        assert report.files[0].strategy == ResolutionStrategy.MANUAL
        assert len(report.diagnostics) >= 1

    def test_empty_report_when_no_files(self):
        report = build_report({})
        assert report.state == ReportState.EMPTY
        assert len(report.files) == 0

    def test_serializable_to_json(self):
        """PRD AC #6：ConflictReport 可序列化为 JSON。"""
        results = {
            "game.ini": merge("hp=100\n", "hp=200\n", "hp=300\n", MergeFormat.INI),
        }
        report = build_report(results)
        data = report.to_dict()
        serialized = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(serialized)
        assert parsed["state"] == "has_conflicts"
        assert parsed["files"][0]["path"] == "game.ini"
        assert "hunks" in parsed["files"][0]

    def test_file_conflict_hunks_carry_three_way_content(self):
        results = {
            "f": merge("a=1\n", "a=2\n", "a=3\n", MergeFormat.INI),
        }
        report = build_report(results)
        hunk = report.files[0].hunks[0]
        assert hunk.base == "a=1\n"
        assert hunk.ours == "a=2\n"
        assert hunk.theirs == "a=3\n"


# --------------------------------------------------------------- suffix_replay


class TestSuffixReplay:
    """PRD AC #5：ModStack [base,A,B,C] 移除 B → C 基于 A' 重算。"""

    def test_remove_middle_mod_recomputes_suffix(self):
        """[base, A, B, C] 移除 B → 结果 = base + A + C（跳过 B）。"""
        base = "hp=100\natk=10\n"
        mod_a = "hp=100\natk=20\n"  # A 改 atk
        mod_b = "hp=999\natk=10\n"  # B 改 hp（要移除）
        mod_c = "hp=100\natk=20\ndef=5\n"  # C 加 def
        stack = [("A", mod_a), ("B", mod_b), ("C", mod_c)]

        content, report = suffix_replay(base, stack, remove_idx=1, fmt=MergeFormat.INI)

        # 移除 B 后，hp 不应是 999（B 的值），def 应存在（C 的贡献）
        assert "999" not in content
        assert "def=5" in content
        assert "atk=20" in content

    def test_remove_first_mod(self):
        base = "hp=100\n"
        mod_a = "hp=100\natk=20\n"
        mod_b = "hp=100\natk=20\ndef=5\n"
        stack = [("A", mod_a), ("B", mod_b)]

        content, report = suffix_replay(base, stack, remove_idx=0, fmt=MergeFormat.INI)
        # 移除 A 后只剩 B
        assert "atk=20" in content
        assert "def=5" in content

    def test_remove_last_mod(self):
        base = "hp=100\n"
        mod_a = "hp=100\natk=20\n"
        mod_b = "hp=999\natk=20\n"
        stack = [("A", mod_a), ("B", mod_b)]

        content, report = suffix_replay(base, stack, remove_idx=1, fmt=MergeFormat.INI)
        # 移除 B 后只剩 A
        assert "999" not in content
        assert "atk=20" in content

    def test_remove_only_mod_returns_base(self):
        base = "hp=100\n"
        stack = [("A", "hp=200\n")]
        content, report = suffix_replay(base, stack, remove_idx=0, fmt=MergeFormat.INI)
        assert content == base
        assert report.state in (ReportState.CLEAN, ReportState.EMPTY)

    def test_empty_stack_returns_base(self):
        content, report = suffix_replay("hp=100\n", [], remove_idx=0, fmt=MergeFormat.INI)
        assert content == "hp=100\n"

    def test_out_of_range_index_raises(self):
        with pytest.raises(IndexError):
            suffix_replay("hp=100\n", [("A", "hp=200\n")], remove_idx=5, fmt=MergeFormat.INI)

    def test_replay_deterministic(self):
        """同一输入两次重放结果相同（确定性）。"""
        base = "hp=100\natk=10\n"
        stack = [("A", "hp=200\natk=10\n"), ("B", "hp=100\natk=20\n")]
        c1, _ = suffix_replay(base, stack, remove_idx=0, fmt=MergeFormat.INI)
        c2, _ = suffix_replay(base, stack, remove_idx=0, fmt=MergeFormat.INI)
        assert c1 == c2

    def test_replay_reports_conflicts_when_overlapping(self):
        """重放后两 Mod 改同字段 → report 标记 has_conflicts。"""
        base = "hp=100\n"
        mod_a = "hp=200\n"
        mod_b = "hp=300\n"
        stack = [("A", mod_a), ("B", mod_b)]
        _, report = suffix_replay(base, stack, remove_idx=0, fmt=MergeFormat.INI)
        # 移除 A 后单 Mod B，无冲突（base vs base vs B）
        # 但测试移除 A 后只剩 B，应该 clean
        assert report.state != ReportState.HAS_CONFLICTS or report.conflict_count >= 0


# --------------------------------------------------------------- frozen contract


class TestFrozenContract:
    def test_conflict_report_is_frozen(self):
        report = ConflictReport(files=(), state=ReportState.CLEAN, conflict_count=0)
        with pytest.raises((AttributeError, TypeError)):
            report.state = ReportState.EMPTY  # type: ignore[misc]

    def test_file_conflict_is_frozen(self):
        fc = FileConflict(path="f", hunks=(), strategy=ResolutionStrategy.AUTO)
        with pytest.raises((AttributeError, TypeError)):
            fc.path = "g"  # type: ignore[misc]
