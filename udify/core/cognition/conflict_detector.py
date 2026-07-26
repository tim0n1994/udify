"""
冲突检测器 (Conflict Detector)

检测用户意图中的矛盾和约束冲突。
参考: ARCHITECTURE-v2.md §4.2 认知层状态机 + §5.3 意图到目标映射
"""

from typing import Any

from udify.core.cognition.intent import ConstraintType, Intent, StructuredIntent
from udify.core.cognition.reference_resolver import ReferenceResolver


class Conflict:
    """冲突表示"""

    def __init__(
        self,
        conflict_type: str,
        description: str,
        severity: str = "medium",  # low, medium, high, critical
        related_items: list[str] = None,
    ):
        self.type = conflict_type
        self.description = description
        self.severity = severity
        self.related_items = related_items or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "severity": self.severity,
            "related_items": self.related_items,
        }


class ConflictDetector:
    """冲突检测器 - 检测意图中的矛盾

    检测类型:
    1. 方向冲突: "增加伤害" + "减少伤害"
    2. 约束冲突: "不要太难" + "像魂系"（魂系很难）
    3. 偏好冲突: 用户不喜欢permadeath，但意图启用它
    4. 数值冲突: 设置HP < 0 或 > 上限
    5. 参考冲突: 多个参考的特征互相矛盾
    """

    # 冲突方向和程度的对立映射
    OPPOSITE_DIRECTIONS = {
        "increase": "decrease",
        "decrease": "increase",
        "boost": "weaken",
        "weaken": "boost",
        "enhance": "reduce",
        "reduce": "enhance",
    }

    # 特征对立映射（用于参考冲突检测）
    OPPOSITE_FEATURES = {
        "high_death_penalty": "low_death_penalty",
        "permadeath": "respawn_system",
        "punishing_difficulty": "casual_difficulty",
        "methodical_combat": "fast_paced_combat",
        "gradual_progression": "rapid_progression",
        "open_world": "linear_world",
        "hardcore": "casual",
    }

    def __init__(self, reference_resolver: ReferenceResolver | None = None):
        self.reference_resolver = reference_resolver

    def detect(self, intent: Intent, structured_intent: StructuredIntent) -> list[Conflict]:
        """检测意图中的所有冲突

        Args:
            intent: 原始意图对象
            structured_intent: 结构化意图对象

        Returns:
            List[Conflict]: 检测到的冲突列表
        """
        conflicts = []

        # 1. 检测方向冲突
        conflicts.extend(self._detect_direction_conflicts(structured_intent))

        # 2. 检测约束冲突
        conflicts.extend(self._detect_constraint_conflicts(structured_intent))

        # 3. 检测偏好冲突
        conflicts.extend(self._detect_preference_conflicts(structured_intent))

        # 4. 检测数值冲突
        conflicts.extend(self._detect_numeric_conflicts(structured_intent))

        # 5. 检测参考冲突
        if self.reference_resolver:
            conflicts.extend(self._detect_reference_conflicts(structured_intent))

        return conflicts

    def _detect_direction_conflicts(self, intent: StructuredIntent) -> list[Conflict]:
        """检测方向冲突（同时要求增加和减少）"""
        conflicts = []

        sub_goals = intent.sub_goals
        processed_pairs = set()

        for i, goal1 in enumerate(sub_goals):
            for j, goal2 in enumerate(sub_goals):
                if i >= j:
                    continue

                # 检查是否是同一目标的不同方向
                if goal1.get("target_mechanic") == goal2.get("target_mechanic"):
                    change1 = goal1.get("change", {})
                    change2 = goal2.get("change", {})

                    type1 = change1.get("type", "")
                    type2 = change2.get("type", "")

                    # 检查是否对立方向
                    if (
                        type1 in self.OPPOSITE_DIRECTIONS
                        and type2 == self.OPPOSITE_DIRECTIONS[type1]
                    ):
                        conflict = Conflict(
                            conflict_type="direction_conflict",
                            description=f"Conflicting directions for {goal1.get('target_mechanic')}: "
                            f"{type1} vs {type2}",
                            severity="high",
                            related_items=[f"sub_goal_{i}", f"sub_goal_{j}"],
                        )
                        conflicts.append(conflict)
                        processed_pairs.add((i, j))

        return conflicts

    def _detect_constraint_conflicts(self, intent: StructuredIntent) -> list[Conflict]:
        """检测约束冲突"""
        conflicts = []

        # 检查 "不要太难" + "像魂系" 的冲突
        constraints = intent.constraints
        references = intent.references

        has_easy_constraint = any(
            c.type == ConstraintType.DIFFICULTY
            and "not too" in c.expression.lower()
            or "easy" in c.expression.lower()
            for c in constraints
        )

        has_hard_reference = any(
            r.name in ["Dark Souls Series", "Elden Ring"]
            or "punishing" in str(r.features).lower()
            or "high_difficulty" in str(r.features).lower()
            for r in references
        )

        if has_easy_constraint and has_hard_reference:
            conflicts.append(
                Conflict(
                    conflict_type="constraint_reference_conflict",
                    description="User wants 'not too hard' but references hardcore games like Dark Souls",
                    severity="medium",
                    related_items=["constraints", "references"],
                )
            )

        return conflicts

    def _detect_preference_conflicts(self, intent: StructuredIntent) -> list[Conflict]:
        """检测偏好冲突"""
        conflicts = []

        preferences = intent.preferences
        sub_goals = intent.sub_goals

        disliked_mechanics = preferences.get("disliked_mechanics", [])

        for i, goal in enumerate(sub_goals):
            target = goal.get("target_mechanic", "")

            # 检查是否启用了用户不喜欢的机制
            if any(mech in target.lower() for mech in [m.lower() for m in disliked_mechanics]):
                conflicts.append(
                    Conflict(
                        conflict_type="preference_violation",
                        description=f"User dislikes {target} but goal enables it",
                        severity="medium",
                        related_items=[f"sub_goal_{i}", "preferences"],
                    )
                )

        return conflicts

    def _detect_numeric_conflicts(self, intent: StructuredIntent) -> list[Conflict]:
        """检测数值冲突"""
        conflicts = []

        sub_goals = intent.sub_goals

        for i, goal in enumerate(sub_goals):
            change = goal.get("change", {})

            if change.get("type") == "set":
                value = change.get("value")

                # 检查不合理数值
                if isinstance(value, (int, float)):
                    if value < 0:
                        conflicts.append(
                            Conflict(
                                conflict_type="invalid_numeric_value",
                                description=f"Negative value {value} for {goal.get('target_mechanic')}",
                                severity="high",
                                related_items=[f"sub_goal_{i}"],
                            )
                        )

                    # 检查极端数值（可能是错误）
                    if value > 1000000:
                        conflicts.append(
                            Conflict(
                                conflict_type="extreme_numeric_value",
                                description=f"Extremely high value {value} for {goal.get('target_mechanic')}",
                                severity="medium",
                                related_items=[f"sub_goal_{i}"],
                            )
                        )

        return conflicts

    def _detect_reference_conflicts(self, intent: StructuredIntent) -> list[Conflict]:
        """检测参考冲突（多个参考的特征互相矛盾）"""
        conflicts = []

        references = intent.references

        # 比较每对参考
        for i, ref1 in enumerate(references):
            for j, ref2 in enumerate(references):
                if i >= j:
                    continue

                features1 = set(ref1.features)
                features2 = set(ref2.features)

                # 检查对立特征
                for feat1 in features1:
                    opposite = self.OPPOSITE_FEATURES.get(feat1)
                    if opposite and opposite in features2:
                        conflicts.append(
                            Conflict(
                                conflict_type="reference_feature_conflict",
                                description=f"Conflicting features between {ref1.name} and {ref2.name}: "
                                f"{feat1} vs {opposite}",
                                severity="low",
                                related_items=[f"reference_{i}", f"reference_{j}"],
                            )
                        )

        return conflicts

    def resolve_conflicts(
        self, intent: StructuredIntent, conflicts: list[Conflict]
    ) -> StructuredIntent:
        """尝试自动解决冲突

        简单的解决策略：
        1. 方向冲突：保留第一个目标，移除对立目标
        2. 约束冲突：调整参考或约束
        3. 记录无法自动解决的冲突
        """
        resolved_intent = intent
        unresolved = []

        for conflict in conflicts:
            if conflict.type == "direction_conflict":
                # 简单策略：保留第一个，移除后面的
                # 在实际应用中，可以询问用户
                pass
            elif conflict.type == "constraint_reference_conflict":
                # 可以降低参考的置信度
                for ref in resolved_intent.references:
                    ref.confidence *= 0.8
            else:
                unresolved.append(conflict)

        # 将未解决的冲突添加到ambiguity_flags
        if unresolved:
            if "unresolved_conflicts" not in resolved_intent.metadata:
                resolved_intent.metadata["unresolved_conflicts"] = []
            resolved_intent.metadata["unresolved_conflicts"].extend(
                [c.to_dict() for c in unresolved]
            )

        return resolved_intent
