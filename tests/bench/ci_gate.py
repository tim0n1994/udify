#!/usr/bin/env python3
"""
CI bench-gate 入口（iter4 M5 PR2，T5-EVAL-CI-LOOP 研究落地）。

用法：
    python3 tests/bench/ci_gate.py              # 检测退化（有退化 exit 1）
    python3 tests/bench/ci_gate.py --freeze      # 冻结/更新基线

在 CI 中作为独立 job 调用：跑 heuristic/resolver/mock_llm 三引擎，
对比 tests/bench/baseline.json，任一指标退化（低于基线 5%）则 block。
首次运行（无基线）退化为 informational（exit 0），需先 --freeze。

设计原则（T5 研究结论）：
- 确定性：mock LLM 离线，同一 case 多跑结果一致。
- 基线 git-tracked：baseline.json 锁定稳定结果，退化即 block。
- 小样本保守：无基线不误 block。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 脚本直接运行时把仓库根加入 sys.path，使 tests.bench 可导入。
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.bench.report import (  # noqa: E402
    BenchReport,
    detect_regression,
    freeze_baseline,
    map_to_prd,
)
from tests.bench.runner import run_ab  # noqa: E402

BASELINE_PATH = Path(__file__).parent / "baseline.json"


def build_report_from_ab(ab: dict) -> BenchReport:
    """把 run_ab() 的 dict 结果转成 BenchReport。"""
    report = BenchReport(case_count=sum(e.get("total", 0) for e in ab.values()) // max(len(ab), 1))
    for engine, metrics in ab.items():
        for metric in ("intent_type_accuracy", "target_precision", "misfire_avoidance"):
            if metric in metrics:
                report.set_metric(engine, metric, float(metrics[metric]))
    return report


def main() -> int:
    if "--freeze" in sys.argv:
        report = build_report_from_ab(run_ab())
        freeze_baseline(report, BASELINE_PATH)
        print(f"frozen baseline -> {BASELINE_PATH}")
        print(report.to_json())
        return 0

    if "--prd" in sys.argv:
        # PRD 反馈映射（M5 PR3）：把 bench 指标映射到 PRD 验收标准
        report = build_report_from_ab(run_ab())
        fb = map_to_prd(report)
        print(fb.to_dict())
        return 0 if fb.all_met else 1

    report = build_report_from_ab(run_ab())
    result = detect_regression(report, BASELINE_PATH, threshold=0.05)
    print(result.to_dict()["findings"])
    print(f"has_regression={result.has_regression} exit_code={result.exit_code}")
    if result.has_regression:
        print("BENCH-GATE: FAIL — metric regression detected", file=sys.stderr)
    else:
        print("BENCH-GATE: PASS")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
