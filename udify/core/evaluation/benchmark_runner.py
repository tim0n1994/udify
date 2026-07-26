"""
UdifyBench 基准测试框架（BENCH-01..03）。

MODULE-ATTACK-MAP-v3 §15：
- BENCH-01: benchmark case schema（可加载）
- BENCH-02: 10 个 miu2d golden cases（覆盖数值/脚本/奖励）
- BENCH-03: benchmark runner（CI 可跑）

把"能力"变成"可回归资产"：每个 case 定义 intent + expected + forbidden +
hard_constraints + probes，runner 跑 miu2d 闭环 + 静态验证 + 运行时探针 +
意图评估，产出可解释的通过/失败报告。

10 个首批 golden case（§15）：见 ``miu2d_cases.py``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from udify.core.evaluation.eval_v3 import EvalResult, GoldenCase, IntentAlignmentEvaluatorV3
from udify.core.miu2d_pipeline import Miu2dClosedLoop
from udify.core.validation.runtime_probe import (
    HeadlessRuntimeProbe,
    ProbeReport,
    probes_for_graph,
)
from udify.core.validation.static_validator import StaticValidatorV3, ValidationReportV3
from udify.models.cdl_patch import CDLPatch
from udify.models.content_graph import ContentGraph


@dataclass
class BenchmarkCase:
    """BENCH-01: benchmark case（含输入游戏 fixture）。"""

    case: GoldenCase
    game_fixture: dict[str, str] = field(default_factory=dict)  # filename → content
    game_root: Path | None = None  # 运行时填充


@dataclass
class CaseResult:
    """单 case 的完整运行结果。"""

    case_id: str
    intent: str
    passed: bool
    loop_success: bool = False
    eval_result: EvalResult | None = None
    static_report: ValidationReportV3 | None = None
    probe_report: ProbeReport | None = None
    patch: CDLPatch | None = None
    graph: ContentGraph | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "intent": self.intent,
            "passed": self.passed,
            "loop_success": self.loop_success,
            "eval": self.eval_result.to_dict() if self.eval_result else None,
            "static": self.static_report.to_dict() if self.static_report else None,
            "probe": self.probe_report.to_dict() if self.probe_report else None,
            "error": self.error,
        }


@dataclass
class BenchmarkReport:
    """BENCH-03: 全部 case 的聚合报告。"""

    results: list[CaseResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    total_score: float = 0.0

    @property
    def all_passed(self) -> bool:
        return self.failed_count == 0 and self.passed_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.all_passed,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "total_score": self.total_score,
            "results": [r.to_dict() for r in self.results],
        }


class BenchmarkRunner:
    """BENCH-03: benchmark runner（CI 可跑）。"""

    def __init__(self) -> None:
        self.evaluator = IntentAlignmentEvaluatorV3()
        self.static_validator = StaticValidatorV3()
        self.probe = HeadlessRuntimeProbe()

    def run_case(self, bench_case: BenchmarkCase) -> CaseResult:
        """运行单个 benchmark case：闭环 → 静态验证 → 探针 → 评估。"""
        case = bench_case.case
        result = CaseResult(case_id=case.case_id, intent=case.intent, passed=False)

        # 准备游戏 fixture
        if bench_case.game_root is None:
            raise ValueError("game_root must be set on BenchmarkCase")

        # 1. miu2d 闭环
        loop = Miu2dClosedLoop(bench_case.game_root)
        loop_result = loop.run(case.intent)
        result.loop_success = loop_result.success
        result.graph = loop_result.graph
        result.patch = loop_result.patch

        if not loop_result.success:
            result.error = "; ".join(loop_result.errors[:3])
            return result

        # 2. 静态验证
        if loop_result.patch and loop_result.graph:
            result.static_report = self.static_validator.validate(
                loop_result.patch, loop_result.graph, loop_result.vfs_diffs
            )
            if not result.static_report.passed:
                result.error = "static_validation_failed"
                return result

        # 3. 运行时探针
        if loop_result.graph:
            probes = probes_for_graph(loop_result.graph)
            result.probe_report = self.probe.run(loop_result.graph, probes, loop_result.vfs_diffs)
            if not result.probe_report.passed:
                result.error = "probe_failed"
                return result

        # 4. 意图对齐评估
        if loop_result.patch:
            result.eval_result = self.evaluator.evaluate(case, loop_result.patch)
            if not result.eval_result.passed:
                result.error = f"eval_failed: {result.eval_result.reject_reason}"
                return result

        result.passed = True
        return result

    def run_all(self, cases: list[BenchmarkCase]) -> BenchmarkReport:
        """运行全部 case。"""
        report = BenchmarkReport()
        for c in cases:
            cr = self.run_case(c)
            report.results.append(cr)
            if cr.passed:
                report.passed_count += 1
                if cr.eval_result:
                    report.total_score += cr.eval_result.total_score
            else:
                report.failed_count += 1
        if report.passed_count > 0:
            report.total_score /= report.passed_count
        return report


def materialize_fixture(case: BenchmarkCase, base_dir: Path) -> Path:
    """把 case 的 game_fixture 写到 base_dir，返回 game_root。"""
    game_root = base_dir / case.case.case_id
    game_root.mkdir(parents=True, exist_ok=True)
    for filename, content in case.game_fixture.items():
        (game_root / filename).write_text(content)
    case.game_root = game_root
    return game_root


def load_cases_from_disk(bench_root: Path) -> list[BenchmarkCase]:
    """从 ``benchmarks/miu2d/<case>/`` 目录布局加载 cases（BENCH-01）。

    布局：``<case>/{input_game/, intent.md, expected_patterns.yaml,
    forbidden_patterns.yaml, scoring.yaml, probes.yaml}``。
    """

    cases: list[BenchmarkCase] = []
    if not bench_root.exists():
        return cases
    for case_dir in sorted(p for p in bench_root.iterdir() if p.is_dir()):
        case_id = case_dir.name
        intent = (case_dir / "intent.md").read_text().strip().split("\n", 1)[-1].strip()
        game_dir = case_dir / "input_game"
        fixture = {}
        if game_dir.exists():
            for f in game_dir.iterdir():
                if f.is_file():
                    fixture[f.name] = f.read_text()
        expected = _safe_yaml_list(case_dir / "expected_patterns.yaml")
        forbidden = _safe_yaml_list(case_dir / "forbidden_patterns.yaml")
        scoring = _safe_yaml(case_dir / "scoring.yaml")
        constraints = scoring.get("hard_constraints", []) if scoring else []
        gc = GoldenCase(
            case_id=case_id,
            intent=intent,
            expected_patterns=expected,
            forbidden_patterns=forbidden,
            hard_constraints=constraints,
        )
        cases.append(BenchmarkCase(case=gc, game_fixture=fixture))
    return cases


def _safe_yaml(path: Path) -> dict:
    import yaml  # type: ignore[import-not-found]

    if not path.exists():
        return {}
    try:
        result = yaml.safe_load(path.read_text())
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _safe_yaml_list(path: Path) -> list:
    import yaml  # type: ignore[import-not-found]

    if not path.exists():
        return []
    try:
        result = yaml.safe_load(path.read_text())
        return result if isinstance(result, list) else []
    except Exception:
        return []


__all__ = [
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkRunner",
    "CaseResult",
    "materialize_fixture",
]
