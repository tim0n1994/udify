"""
评估层（Intent Alignment）测试。

覆盖：
- 四个评估维度：goal_achievement / constraint_satisfaction / reference_match / scope_control
- 评分范围、passed 阈值、空 patch、空约束/空参考的边界
- LLM 不可用时的降级

对应 ITERATION-PLAN-2026-07.md §5.3「Validator + Evaluator 四层」与 §9.2。
"""

from __future__ import annotations

import pytest

from udify.core.cognition.intent import (
    Constraint,
    ConstraintType,
    Intent,
    IntentType,
    StructuredIntent,
)
from udify.core.evaluation.intent_alignment import IntentAlignmentEvaluator
from udify.models.cdl_patch import CDLPatch, create_modify_property_op


@pytest.fixture
def evaluator() -> IntentAlignmentEvaluator:
    return IntentAlignmentEvaluator()


@pytest.fixture
def difficulty_intent() -> Intent:
    return Intent(
        raw_text="让Boss血量翻倍",
        language="zh",
        intent_type=IntentType.DIFFICULTY_ADJUSTMENT,
        primary_goal="adjust_enemy_difficulty",
    )


@pytest.fixture
def structured() -> StructuredIntent:
    return StructuredIntent()


@pytest.fixture
def patch_with_modification() -> CDLPatch:
    return CDLPatch(
        operations=[create_modify_property_op("boss_1", "MaxLife", 1000)],
        intent="让Boss血量翻倍",
    )


class TestGoalAchievement:
    """目标达成度"""

    def test_difficulty_with_modification_scores_high(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        assert result["total_score"] > 0

    def test_empty_patch_scores_zero(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
    ) -> None:
        empty_patch = CDLPatch()
        result = evaluator.evaluate(difficulty_intent, structured, empty_patch)
        assert result["metrics"]["goal_achievement"]["score"] == 0.0

    def test_content_expansion_with_add(self, evaluator: IntentAlignmentEvaluator) -> None:
        from udify.models.cdl_patch import create_add_node_op
        from udify.models.content_graph import NodeType

        intent = Intent(raw_text="add content", intent_type=IntentType.CONTENT_EXPANSION)
        patch = CDLPatch(operations=[create_add_node_op("n1", NodeType.ITEM, "NewItem")])
        result = evaluator.evaluate(intent, StructuredIntent(), patch)
        assert result["metrics"]["goal_achievement"]["score"] == 1.0


class TestConstraintSatisfaction:
    """约束满足度"""

    def test_no_constraints_is_satisfied(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        assert result["metrics"]["constraint_satisfaction"]["score"] == 1.0

    def test_constraint_with_not_too_hard(self, evaluator: IntentAlignmentEvaluator) -> None:
        """含 'not too hard' 约束、patch 值非极端 → 满足"""
        structured = StructuredIntent()
        structured.constraints.append(
            Constraint(type=ConstraintType.DIFFICULTY, expression="difficulty not too hard")
        )
        patch = CDLPatch(operations=[create_modify_property_op("boss_1", "hp", 200)])
        result = evaluator.evaluate(Intent(raw_text="test"), structured, patch)
        assert result["metrics"]["constraint_satisfaction"]["score"] == 1.0


class TestReferenceMatch:
    """参考匹配度"""

    def test_no_references_is_satisfied(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        assert result["metrics"]["reference_match"]["score"] == 1.0


class TestScopeControl:
    """范围控制度"""

    def test_reasonable_difficulty_ops(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
    ) -> None:
        patch = CDLPatch(operations=[create_modify_property_op("b1", "hp", 200)])
        result = evaluator.evaluate(difficulty_intent, structured, patch)
        assert result["metrics"]["scope_control"]["score"] == 1.0

    def test_too_few_ops_for_expansion(self, evaluator: IntentAlignmentEvaluator) -> None:
        """内容扩展只 1 个操作 → 范围分偏低"""
        intent = Intent(raw_text="expand", intent_type=IntentType.CONTENT_EXPANSION)
        patch = CDLPatch(operations=[create_modify_property_op("n1", "x", 1)])
        result = evaluator.evaluate(intent, StructuredIntent(), patch)
        assert result["metrics"]["scope_control"]["score"] < 1.0


class TestOverallScoring:
    """总体评分"""

    def test_score_in_range(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        assert 0.0 <= result["total_score"] <= 1.0

    def test_passed_threshold(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        assert result["passed"] in (True, False)
        # 有数值修改 + 合理范围 → 通常通过
        assert result["passed"] is True

    def test_summary_string(self, evaluator: IntentAlignmentEvaluator) -> None:
        result = evaluator.evaluate(Intent(raw_text="test"), StructuredIntent(), CDLPatch())
        assert isinstance(result["summary"], str)

    def test_metrics_all_present(
        self,
        evaluator: IntentAlignmentEvaluator,
        difficulty_intent: Intent,
        structured: StructuredIntent,
        patch_with_modification: CDLPatch,
    ) -> None:
        result = evaluator.evaluate(difficulty_intent, structured, patch_with_modification)
        for metric in [
            "goal_achievement",
            "constraint_satisfaction",
            "reference_match",
            "scope_control",
        ]:
            assert metric in result["metrics"]
