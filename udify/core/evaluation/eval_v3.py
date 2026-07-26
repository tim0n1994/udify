"""
意图对齐评估 v3（EVAL-INTENT-01..04）。

MODULE-ATTACK-MAP-v3 §9 EVAL-INTENT：
- EVAL-INTENT-01: golden case format（intent、expected、forbidden）
- EVAL-INTENT-02: goal achievement score（可解释）
- EVAL-INTENT-03: constraint satisfaction（hard constraint 失败即 reject）
- EVAL-INTENT-04: scope control（过度修改扣分）

这是 UdifyBench 的评分核心：给定一个 golden case（期望/禁止模式）和一个 patch，
产出可解释的对齐分。LLM judge 仅可选、不单独决定通过（EVAL-INTENT-06）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from udify.models.cdl_patch import CDLPatch


@dataclass
class GoldenCase:
    """EVAL-INTENT-01: golden case 格式。

    Attributes:
        case_id: 案例标识。
        intent: 自然语言意图。
        expected_patterns: 期望在 patch 中出现的模式（键值/操作）。
        forbidden_patterns: 禁止出现的模式（如危险 API、极端数值）。
        hard_constraints: 硬约束（失败即 reject，如 "factor <= 1.35"）。
        probes: 关联的运行时探针期望。
    """

    case_id: str
    intent: str
    expected_patterns: list[dict[str, Any]] = field(default_factory=list)
    forbidden_patterns: list[dict[str, Any]] = field(default_factory=list)
    hard_constraints: list[str] = field(default_factory=list)
    probes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EvalResult:
    """单案例评估结果。"""

    case_id: str
    passed: bool
    goal_achievement: float = 0.0
    constraint_satisfaction: float = 0.0
    scope_control: float = 0.0
    total_score: float = 0.0
    reject_reason: str = ""
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "passed": self.passed,
            "total_score": self.total_score,
            "goal_achievement": self.goal_achievement,
            "constraint_satisfaction": self.constraint_satisfaction,
            "scope_control": self.scope_control,
            "reject_reason": self.reject_reason,
            "findings": self.findings,
        }


class IntentAlignmentEvaluatorV3:
    """意图对齐评估器 v3（EVAL-INTENT-02..04）。"""

    # 权重（§5.3 EVAL）
    W_GOAL = 0.45
    W_CONSTRAINT = 0.30
    W_SCOPE = 0.25

    def evaluate(self, case: GoldenCase, patch: CDLPatch) -> EvalResult:
        """评估一个 patch 对 golden case 的对齐度。"""
        result = EvalResult(case_id=case.case_id, passed=True)

        # EVAL-INTENT-02: goal achievement
        result.goal_achievement = self._score_goal(case, patch)
        # EVAL-INTENT-03: constraint satisfaction（hard constraint 失败即 reject）
        result.constraint_satisfaction, hard_fail = self._score_constraints(case, patch)
        if hard_fail:
            result.passed = False
            result.reject_reason = "hard_constraint_violated"
        # EVAL-INTENT-04: scope control
        result.scope_control = self._score_scope(case, patch)

        # forbidden 模式检查
        forbidden_hit = self._check_forbidden(case, patch)
        if forbidden_hit:
            result.passed = False
            result.reject_reason = "forbidden_pattern_present"
            result.findings.append(forbidden_hit)

        result.total_score = (
            self.W_GOAL * result.goal_achievement
            + self.W_CONSTRAINT * result.constraint_satisfaction
            + self.W_SCOPE * result.scope_control
        )
        result.total_score = min(1.0, max(0.0, result.total_score))

        if result.total_score < 0.6 and result.passed:
            result.passed = False
            result.reject_reason = "score_below_threshold"

        return result

    def _score_goal(self, case: GoldenCase, patch: CDLPatch) -> float:
        """EVAL-INTENT-02: 期望模式命中率。"""
        if not case.expected_patterns:
            return 1.0 if patch.operations else 0.0
        patch_blob = self._patch_blob(patch)
        hit = 0
        for pattern in case.expected_patterns:
            if self._pattern_matches(pattern, patch_blob, patch):
                hit += 1
        return hit / len(case.expected_patterns) if case.expected_patterns else 1.0

    def _score_constraints(self, case: GoldenCase, patch: CDLPatch) -> tuple[float, bool]:
        """EVAL-INTENT-03: 硬约束检查。返回 (分数, 是否有硬约束失败)。"""
        from udify.core.text_normalize import extract_attr_from_patch, parse_constraint

        if not case.hard_constraints:
            return (1.0, False)

        satisfied = 0
        hard_fail = False
        for constraint in case.hard_constraints:
            expr = parse_constraint(constraint)
            if expr is None:
                continue
            actual = extract_attr_from_patch(patch.operations, expr.attr)
            if actual is None:
                continue
            if expr.evaluate(actual):
                satisfied += 1
            else:
                hard_fail = True
        return (satisfied / len(case.hard_constraints), hard_fail)

    def _score_scope(self, case: GoldenCase, patch: CDLPatch) -> float:
        """EVAL-INTENT-04: 范围控制（操作数合理即高分）。"""
        n = len(patch.operations)
        if n == 0:
            return 0.0
        if 1 <= n <= 20:
            return 1.0
        if n <= 50:
            return 0.6
        return 0.3

    def _check_forbidden(self, case: GoldenCase, patch: CDLPatch) -> str | None:
        """检查禁止模式。"""
        blob = self._patch_blob(patch)
        for pattern in case.forbidden_patterns:
            if self._pattern_matches(pattern, blob, patch):
                return f"forbidden pattern matched: {pattern}"
        return None

    def _patch_blob(self, patch: CDLPatch) -> str:
        return str(
            [
                {
                    "op": op.op_type.name,
                    "target": op.target_id,
                    "payload": op.payload,
                }
                for op in patch.operations
            ]
        ).lower()

    def _pattern_matches(self, pattern: dict[str, Any], blob: str, patch: CDLPatch) -> bool:
        """检查模式是否匹配（支持 key/value/op/command 子模式）。"""
        for key, val in pattern.items():
            val_str = str(val).lower()
            if key == "op" or key == "command" or key == "key":
                if val_str not in blob:
                    return False
            else:
                if val_str not in blob and val_str not in str(patch).lower():
                    return False
        return True


__all__ = ["EvalResult", "GoldenCase", "IntentAlignmentEvaluatorV3"]
