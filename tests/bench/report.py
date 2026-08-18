"""
评测报告与基线退化检测（iter4 M5，T5-EVAL-CI-LOOP 研究落地）。

把 bench 的 A/B 结果固化成 JSON 报告 + 基线冻结 + 退化检测。
退化即 block：指标低于基线阈值则报告退化。

设计原则（T5 研究结论）：
- 确定性：同一 case 多跑结果一致（mock LLM 离线）。
- 基线 git-tracked：baseline.json 锁定首次稳定结果。
- 退化检测：指标 delta + 阈值，小样本下保守（宁可 informational 也不误 block）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineMetric:
    """单引擎单指标的基线值。"""

    engine: str
    metric: str  # intent_type_accuracy / target_precision / misfire_avoidance
    value: float


@dataclass
class BenchReport:
    """评测报告（可序列化 JSON）。"""

    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    engines: dict[str, dict[str, float]] = field(default_factory=dict)  # engine -> metric -> value
    case_count: int = 0

    def set_metric(self, engine: str, metric: str, value: float) -> None:
        self.engines.setdefault(engine, {})[metric] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "case_count": self.case_count,
            "engines": self.engines,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass(frozen=True)
class RegressionFinding:
    """单条退化发现。"""

    engine: str
    metric: str
    baseline: float
    actual: float
    delta: float
    threshold: float
    regressed: bool  # 是否真退化（低于 baseline - threshold）

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RegressionReport:
    """退化检测报告。"""

    findings: tuple[RegressionFinding, ...]
    has_regression: bool

    @property
    def exit_code(self) -> int:
        """CI 用：有退化返回 1（block），否则 0。"""
        return 1 if self.has_regression else 0

    def to_dict(self) -> dict:
        return {
            "has_regression": self.has_regression,
            "exit_code": self.exit_code,
            "findings": [f.to_dict() for f in self.findings],
        }


def freeze_baseline(report: BenchReport, path: str | Path) -> None:
    """把报告冻结成基线文件（git-tracked）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(report.to_json(), encoding="utf-8")


def load_baseline(path: str | Path) -> dict[str, Any]:
    """加载基线文件。不存在返回空。"""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def detect_regression(
    actual: BenchReport,
    baseline_path: str | Path,
    threshold: float = 0.05,
) -> RegressionReport:
    """检测实际结果相对基线的退化。

    Args:
        actual: 本次评测报告。
        baseline_path: 基线 JSON 路径。
        threshold: 退化阈值（指标下降超过此比例算退化）。

    Returns:
        RegressionReport。无基线时所有指标 informational（不退化）。
    """
    baseline = load_baseline(baseline_path)
    baseline_engines = baseline.get("engines", {})
    findings: list[RegressionFinding] = []
    has_regression = False

    for engine, metrics in actual.engines.items():
        base_metrics = baseline_engines.get(engine, {})
        for metric, value in metrics.items():
            base_value = base_metrics.get(metric)
            if base_value is None:
                # 无基线：informational，不退化
                findings.append(
                    RegressionFinding(engine, metric, 0.0, value, 0.0, threshold, False)
                )
                continue
            delta = value - base_value
            regressed = delta < -threshold
            if regressed:
                has_regression = True
            findings.append(
                RegressionFinding(engine, metric, base_value, value, delta, threshold, regressed)
            )

    return RegressionReport(findings=tuple(findings), has_regression=has_regression)


# ============================================================
# PRD 反馈映射（iter4 M5 PR3，T5-EVAL-CI-LOOP）
# ============================================================


@dataclass(frozen=True)
class PrdCriterionCheck:
    """单条 PRD 验收标准的达成状态。"""

    criterion_id: str
    description: str
    met: bool
    evidence: str = ""

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id,
            "description": self.description,
            "met": self.met,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class PrdFeedbackReport:
    """把 bench 结果映射到 PRD 验收标准的反馈报告。

    PRD M5 职责：「建立基线冻结 + 退化检测 + PRD 反馈闭环」。
    此函数让 bench 的指标结果直接回答「PRD 的验收标准是否达成」。
    """

    criteria: tuple[PrdCriterionCheck, ...]
    all_met: bool

    @property
    def met_count(self) -> int:
        return sum(1 for c in self.criteria if c.met)

    @property
    def unmet(self) -> tuple[PrdCriterionCheck, ...]:
        return tuple(c for c in self.criteria if not c.met)

    def to_dict(self) -> dict:
        return {
            "all_met": self.all_met,
            "met_count": self.met_count,
            "total": len(self.criteria),
            "criteria": [c.to_dict() for c in self.criteria],
        }


def map_to_prd(report: BenchReport) -> PrdFeedbackReport:
    """把 BenchReport 的引擎指标映射到 PRD 验收标准。

    映射逻辑（基于 T5 研究 + PRD AC）：
    - intent_type_accuracy >= 0.4 → 意图分类基础达标（heuristic 已验证）
    - target_precision >= 0.9 → 目标定位精度达标（resolver 已验证）
    - misfire_avoidance >= 0.9 → 误伤控制达标
    - 三引擎均有结果 → A/B 对照完整
    - case_count >= 30 → 评测覆盖充分
    """
    criteria: list[PrdCriterionCheck] = []
    engines = report.engines

    # AC: 意图分类基础（heuristic 的 intent_type_accuracy）
    heur_acc = engines.get("heuristic", {}).get("intent_type_accuracy", 0.0)
    criteria.append(
        PrdCriterionCheck(
            "intent-baseline",
            "意图分类基础准确率（heuristic >= 0.4）",
            heur_acc >= 0.4,
            f"heuristic.intent_type_accuracy={heur_acc:.3f}",
        )
    )

    # AC: 目标定位精度（resolver）
    res_prec = engines.get("resolver", {}).get("target_precision", 0.0)
    criteria.append(
        PrdCriterionCheck(
            "target-precision",
            "目标定位精度（resolver >= 0.9）",
            res_prec >= 0.9,
            f"resolver.target_precision={res_prec:.3f}",
        )
    )

    # AC: 误伤控制
    res_misfire = engines.get("resolver", {}).get("misfire_avoidance", 0.0)
    criteria.append(
        PrdCriterionCheck(
            "misfire-avoidance",
            "误伤控制（resolver misfire_avoidance >= 0.9）",
            res_misfire >= 0.9,
            f"resolver.misfire_avoidance={res_misfire:.3f}",
        )
    )

    # AC: A/B 对照完整（三引擎均存在）
    has_three = len(engines) >= 3
    criteria.append(
        PrdCriterionCheck(
            "ab-completeness",
            "A/B 对照完整（heuristic + resolver + mock_llm 三引擎）",
            has_three,
            f"engines={list(engines.keys())}",
        )
    )

    # AC: 评测覆盖充分（case_count >= 30）
    criteria.append(
        PrdCriterionCheck(
            "case-coverage",
            "评测覆盖充分（>= 30 case）",
            report.case_count >= 30,
            f"case_count={report.case_count}",
        )
    )

    all_met = all(c.met for c in criteria)
    return PrdFeedbackReport(criteria=tuple(criteria), all_met=all_met)
