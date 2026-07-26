"""
评估层 (Evaluation Layer)

评估改造结果的质量和对齐度。
"""

from udify.core.evaluation.intent_alignment import AlignmentMetric, IntentAlignmentEvaluator

__all__ = ["IntentAlignmentEvaluator", "AlignmentMetric"]
