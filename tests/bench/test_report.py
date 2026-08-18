"""iter4 M5 — 评测报告与基线退化检测测试。"""

from __future__ import annotations

import json

from tests.bench.report import (
    BenchReport,
    RegressionReport,
    detect_regression,
    freeze_baseline,
    load_baseline,
)


def test_bench_report_set_and_serialize():
    r = BenchReport(case_count=30)
    r.set_metric("resolver", "target_precision", 1.0)
    r.set_metric("heuristic", "target_precision", 0.067)
    d = r.to_dict()
    assert d["case_count"] == 30
    assert d["engines"]["resolver"]["target_precision"] == 1.0
    s = r.to_json()
    assert json.loads(s)["engines"]["heuristic"]["target_precision"] == 0.067


def test_freeze_and_load_baseline(tmp_path):
    r = BenchReport(case_count=30)
    r.set_metric("resolver", "target_precision", 1.0)
    p = tmp_path / "baseline.json"
    freeze_baseline(r, p)
    assert p.exists()
    loaded = load_baseline(p)
    assert loaded["engines"]["resolver"]["target_precision"] == 1.0


def test_load_baseline_missing_returns_empty(tmp_path):
    assert load_baseline(tmp_path / "nope.json") == {}


def test_detect_regression_no_baseline_informational(tmp_path):
    actual = BenchReport(case_count=30)
    actual.set_metric("resolver", "target_precision", 0.5)
    rep = detect_regression(actual, tmp_path / "baseline.json", threshold=0.05)
    assert not rep.has_regression
    assert rep.exit_code == 0
    # 无基线的指标 informational（regressed=False）
    assert all(not f.regressed for f in rep.findings)


def test_detect_regression_when_metric_drops(tmp_path):
    # 冻结一个高基线
    base = BenchReport(case_count=30)
    base.set_metric("resolver", "target_precision", 1.0)
    bp = tmp_path / "baseline.json"
    freeze_baseline(base, bp)
    # 实际下降到 0.8（delta -0.2 < -0.05 阈值）
    actual = BenchReport(case_count=30)
    actual.set_metric("resolver", "target_precision", 0.8)
    rep = detect_regression(actual, bp, threshold=0.05)
    assert rep.has_regression
    assert rep.exit_code == 1
    regressed = [f for f in rep.findings if f.regressed]
    assert len(regressed) == 1
    assert round(regressed[0].delta, 6) == round(-0.2, 6)  # float-safe


def test_detect_regression_no_regression_when_improves(tmp_path):
    base = BenchReport(case_count=30)
    base.set_metric("resolver", "target_precision", 0.8)
    bp = tmp_path / "baseline.json"
    freeze_baseline(base, bp)
    actual = BenchReport(case_count=30)
    actual.set_metric("resolver", "target_precision", 1.0)  # 提升
    rep = detect_regression(actual, bp, threshold=0.05)
    assert not rep.has_regression
    assert rep.exit_code == 0


def test_regression_report_to_dict():
    r = RegressionReport(findings=(), has_regression=False)
    d = r.to_dict()
    assert d["has_regression"] is False
    assert d["exit_code"] == 0
