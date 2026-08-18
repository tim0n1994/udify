"""iter4 M5 PR2 — bench-gate CI 入口测试。"""

from __future__ import annotations

from tests.bench.ci_gate import build_report_from_ab
from tests.bench.report import BenchReport, PrdCriterionCheck, detect_regression, map_to_prd


def test_build_report_from_ab_extracts_metrics():
    ab = {
        "heuristic": {
            "intent_type_accuracy": 0.47,
            "target_precision": 0.07,
            "misfire_avoidance": 0.9,
            "total": 30,
        },
        "resolver": {
            "intent_type_accuracy": 0.4,
            "target_precision": 1.0,
            "misfire_avoidance": 1.0,
            "total": 30,
        },
    }
    report = build_report_from_ab(ab)
    assert report.engines["heuristic"]["intent_type_accuracy"] == 0.47
    assert report.engines["resolver"]["target_precision"] == 1.0
    assert report.case_count > 0


def test_build_report_skips_missing_metrics():
    ab = {"partial": {"intent_type_accuracy": 0.5, "total": 10}}
    report = build_report_from_ab(ab)
    assert "intent_type_accuracy" in report.engines["partial"]
    assert "target_precision" not in report.engines["partial"]


def test_gate_passes_when_metrics_match_baseline(tmp_path):
    """指标与基线一致 → 无退化。"""
    from tests.bench.report import BenchReport, freeze_baseline

    report = BenchReport(case_count=30)
    report.set_metric("heuristic", "intent_type_accuracy", 0.47)
    baseline_file = tmp_path / "baseline.json"
    freeze_baseline(report, baseline_file)

    actual = BenchReport(case_count=30)
    actual.set_metric("heuristic", "intent_type_accuracy", 0.47)
    result = detect_regression(actual, baseline_file, threshold=0.05)
    assert result.has_regression is False
    assert result.exit_code == 0


def test_gate_blocks_on_regression(tmp_path):
    """指标低于基线阈值 → 退化，exit 1。"""
    from tests.bench.report import BenchReport, freeze_baseline

    report = BenchReport(case_count=30)
    report.set_metric("resolver", "target_precision", 1.0)
    baseline_file = tmp_path / "baseline.json"
    freeze_baseline(report, baseline_file)

    actual = BenchReport(case_count=30)
    actual.set_metric("resolver", "target_precision", 0.90)  # -0.10 > threshold 0.05
    result = detect_regression(actual, baseline_file, threshold=0.05)
    assert result.has_regression is True
    assert result.exit_code == 1


def test_gate_informational_without_baseline(tmp_path):
    """无基线文件 → informational，不退化。"""
    from tests.bench.report import BenchReport

    actual = BenchReport(case_count=30)
    actual.set_metric("heuristic", "intent_type_accuracy", 0.47)
    result = detect_regression(actual, tmp_path / "nonexistent.json", threshold=0.05)
    assert result.has_regression is False


# ============================================================
# PRD 反馈映射测试（iter4 M5 PR3）
# ============================================================


class TestPrdFeedbackMapping:
    def test_all_criteria_met_when_metrics_strong(self):
        report = BenchReport(case_count=30)
        report.set_metric("heuristic", "intent_type_accuracy", 0.47)
        report.set_metric("resolver", "target_precision", 1.0)
        report.set_metric("resolver", "misfire_avoidance", 1.0)
        report.set_metric("mock_llm", "intent_type_accuracy", 0.4)
        fb = map_to_prd(report)
        assert fb.all_met is True
        assert fb.met_count == 5

    def test_flags_low_intent_accuracy(self):
        report = BenchReport(case_count=30)
        report.set_metric("heuristic", "intent_type_accuracy", 0.2)
        report.set_metric("resolver", "target_precision", 1.0)
        report.set_metric("resolver", "misfire_avoidance", 1.0)
        report.set_metric("mock_llm", "intent_type_accuracy", 0.2)
        fb = map_to_prd(report)
        intent_check = [c for c in fb.criteria if c.criterion_id == "intent-baseline"][0]
        assert intent_check.met is False
        assert fb.all_met is False

    def test_flags_missing_engines(self):
        report = BenchReport(case_count=30)
        report.set_metric("heuristic", "intent_type_accuracy", 0.47)
        fb = map_to_prd(report)
        ab_check = [c for c in fb.criteria if c.criterion_id == "ab-completeness"][0]
        assert ab_check.met is False

    def test_flags_low_case_coverage(self):
        report = BenchReport(case_count=10)
        report.set_metric("heuristic", "intent_type_accuracy", 0.47)
        report.set_metric("resolver", "target_precision", 1.0)
        report.set_metric("resolver", "misfire_avoidance", 1.0)
        report.set_metric("mock_llm", "intent_type_accuracy", 0.4)
        fb = map_to_prd(report)
        coverage_check = [c for c in fb.criteria if c.criterion_id == "case-coverage"][0]
        assert coverage_check.met is False

    def test_unmet_property_lists_only_unmet(self):
        report = BenchReport(case_count=5)
        report.set_metric("heuristic", "intent_type_accuracy", 0.47)
        fb = map_to_prd(report)
        assert len(fb.unmet) >= 1
        assert all(not c.met for c in fb.unmet)

    def test_report_serializable(self):
        report = BenchReport(case_count=30)
        report.set_metric("heuristic", "intent_type_accuracy", 0.47)
        report.set_metric("resolver", "target_precision", 1.0)
        report.set_metric("resolver", "misfire_avoidance", 1.0)
        report.set_metric("mock_llm", "intent_type_accuracy", 0.4)
        fb = map_to_prd(report)
        d = fb.to_dict()
        assert "all_met" in d
        assert "criteria" in d
        assert len(d["criteria"]) == 5

    def test_prd_criterion_check_is_frozen(self):
        import pytest

        c = PrdCriterionCheck("a", "b", True, "e")
        with pytest.raises((AttributeError, TypeError)):
            c.met = False  # type: ignore[misc]
