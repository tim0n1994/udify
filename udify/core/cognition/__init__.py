"""
认知层 (Cognition Layer)

将用户意图转化为机器可执行的结构化意图。
"""

from udify.core.cognition.conflict_detector import ConflictDetector
from udify.core.cognition.intent import Constraint, Intent, Reference, StructuredIntent
from udify.core.cognition.intent_classifier import IntentClassifier
from udify.core.cognition.reference_resolver import ReferenceResolver

__all__ = [
    "IntentClassifier",
    "ReferenceResolver",
    "ConflictDetector",
    "StructuredIntent",
    "Intent",
    "Constraint",
    "Reference",
]
