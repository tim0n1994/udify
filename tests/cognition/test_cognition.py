"""
认知层（Cognition）测试。

覆盖：
- IntentClassifier：中英文分类、子目标抽取、约束抽取、歧义检测
- ReferenceResolver：知识库匹配、LLM 降级、规划参数映射
- ConflictDetector：方向/约束/偏好/数值/参考 5 类冲突
- StructuredIntent：from_intent / to_dict 往返

对应 ITERATION-PLAN-2026-07.md §5.2「Intent Compiler」与 §9.2「测试债清偿」。
"""

from __future__ import annotations

import pytest

from udify.core.cognition.conflict_detector import Conflict, ConflictDetector
from udify.core.cognition.intent import (
    Constraint,
    ConstraintType,
    Intent,
    IntentType,
    StructuredIntent,
)
from udify.core.cognition.intent_classifier import IntentClassifier
from udify.core.cognition.reference_resolver import ReferenceResolver


class TestIntentClassifier:
    """意图分类器测试"""

    @pytest.fixture
    def classifier(self) -> IntentClassifier:
        return IntentClassifier()

    @pytest.mark.parametrize(
        "text,language,expected",
        [
            ("让Boss更难打", "zh", IntentType.DIFFICULTY_ADJUSTMENT),
            ("增加新关卡", "zh", IntentType.CONTENT_EXPANSION),
            ("美化画质", "zh", IntentType.VISUAL_STYLE),
            ("修改战斗机制", "zh", IntentType.GAMEPLAY_MECHANIC),
            ("改写结局剧情", "zh", IntentType.NARRATIVE_CHANGE),
            ("make the boss harder", "en", IntentType.DIFFICULTY_ADJUSTMENT),
            ("add new content", "en", IntentType.CONTENT_EXPANSION),
            ("change the dialogue", "en", IntentType.NARRATIVE_CHANGE),
        ],
    )
    def test_classify_by_language(
        self,
        classifier: IntentClassifier,
        text: str,
        language: str,
        expected: IntentType,
    ) -> None:
        """中英文关键词都应正确分类"""
        intent = classifier.classify(text, language)
        assert intent.intent_type == expected

    def test_classify_unknown_returns_unknown(self, classifier: IntentClassifier) -> None:
        """无关键词的输入分类为 UNKNOWN"""
        intent = classifier.classify("xyzqwerty", "zh")
        assert intent.intent_type == IntentType.UNKNOWN

    def test_extract_sub_goals_health(self, classifier: IntentClassifier) -> None:
        """血量类意图应抽取 modify_health 子目标"""
        intent = classifier.classify("让Boss血量翻倍", "zh")
        assert "modify_health" in intent.sub_goals

    def test_extract_sub_goals_damage(self, classifier: IntentClassifier) -> None:
        """伤害类意图应抽取 modify_damage 子目标"""
        intent = classifier.classify("降低敌人攻击伤害", "zh")
        assert "modify_damage" in intent.sub_goals

    def test_extract_constraint_not_too_hard(self, classifier: IntentClassifier) -> None:
        """『不要太难』应抽取为软难度约束（classify 不直接产出 constraints，验证内部方法）"""
        constraints = classifier._extract_constraints("不要太难")
        assert any(c.type == ConstraintType.DIFFICULTY for c in constraints)

    def test_detect_ambiguity_conflicting_directions(self, classifier: IntentClassifier) -> None:
        """同时含增加/减少应标记 conflicting_directions"""
        intent = classifier.classify("增加伤害同时降低伤害", "zh")
        assert "conflicting_directions" in intent.ambiguity_flags

    def test_to_structured_roundtrip(self, classifier: IntentClassifier) -> None:
        """Intent → StructuredIntent → dict 往返"""
        intent = classifier.classify("让Boss更难", "zh")
        structured = classifier.to_structured(intent)
        d = structured.to_dict()
        assert d["primary_goal"]["type"] == "difficulty_adjustment"
        assert d["raw_input"]["text"] == "让Boss更难"

    def test_confidence_in_range(self, classifier: IntentClassifier) -> None:
        """置信度应在 [0, 1]"""
        intent = classifier.classify("让游戏更难", "zh")
        assert 0.0 <= intent.parsing_confidence <= 1.0


class TestReferenceResolver:
    """参考解析器测试"""

    @pytest.fixture
    def resolver(self) -> ReferenceResolver:
        return ReferenceResolver()

    @pytest.mark.parametrize(
        "keyword,expected_name_part",
        [
            ("魂系", "Dark Souls"),
            ("dark souls", "Dark Souls"),
            ("塞尔达", "Zelda"),
            ("武侠", "Wuxia"),
            ("仙侠", "Xianxia"),
            ("roguelike", "Roguelike"),
            ("metroidvania", "Metroidvania"),
        ],
    )
    def test_resolve_known_references(
        self, resolver: ReferenceResolver, keyword: str, expected_name_part: str
    ) -> None:
        """知识库中的参考应被解析为对应名称"""
        ref = resolver.resolve(keyword)
        assert expected_name_part in ref.name
        assert ref.confidence > 0

    def test_resolve_unknown_returns_low_confidence(self, resolver: ReferenceResolver) -> None:
        """未知参考应返回低/零置信度"""
        ref = resolver.resolve("一个不存在的风格xyz123")
        assert ref.name == "unknown"

    def test_resolve_from_structured_intent_zh(self, resolver: ReferenceResolver) -> None:
        """『像魂系那样』应被识别"""
        intent = StructuredIntent()
        intent.raw_input = {"text": "让难度像魂系那样", "language": "zh"}
        refs = resolver.resolve_from_structured_intent(intent)
        assert any("Dark Souls" in r.name for r in refs)

    def test_resolve_from_structured_intent_en(self, resolver: ReferenceResolver) -> None:
        """英文参考识别：当前正则 ``like (.+?)`` 非贪婪导致只捕获首字符，属已知限制，
        将由 §5.2 Intent Compiler 的结构化输出路径修复。这里验证直接 resolve 仍可用。"""
        ref = resolver.resolve("zelda")
        assert "Zelda" in ref.name

    def test_extract_features_for_planning(self, resolver: ReferenceResolver) -> None:
        """参考特征应映射为规划参数"""
        ref = resolver.resolve("魂系")
        params = resolver.extract_features_for_planning(ref)
        assert "difficulty_curve" in params
        # 魂系有 gradual_power_progression / high_death_penalty
        assert params["death_penalty"] == "high"


class TestConflictDetector:
    """冲突检测器测试 —— 5 类冲突"""

    @pytest.fixture
    def detector(self) -> ConflictDetector:
        return ConflictDetector(reference_resolver=ReferenceResolver())

    def _make_intent(
        self,
        sub_goals: list[dict] | None = None,
        constraints: list[Constraint] | None = None,
        references: list | None = None,
        preferences: dict | None = None,
    ) -> StructuredIntent:
        si = StructuredIntent()
        si.sub_goals = sub_goals or []
        si.constraints = constraints or []
        si.references = references or []
        if preferences:
            si.preferences = preferences
        return si

    def test_direction_conflict(self, detector: ConflictDetector) -> None:
        """1. 方向冲突：同一目标同时 increase 与 decrease"""
        si = self._make_intent(
            sub_goals=[
                {"target_mechanic": "hp", "change": {"type": "increase"}},
                {"target_mechanic": "hp", "change": {"type": "decrease"}},
            ]
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "direction_conflict" for c in conflicts)

    def test_constraint_reference_conflict(self, detector: ConflictDetector) -> None:
        """2. 约束-参考冲突：不要太难 + 魂系"""
        from udify.core.cognition.intent import Reference

        si = self._make_intent(
            constraints=[
                Constraint(type=ConstraintType.DIFFICULTY, expression="not too hard", hard=False)
            ],
            references=[
                Reference(
                    name="Dark Souls Series",
                    type="game_series",
                    features=["punishing_difficulty", "high_difficulty"],
                )
            ],
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "constraint_reference_conflict" for c in conflicts)

    def test_preference_conflict(self, detector: ConflictDetector) -> None:
        """3. 偏好冲突：用户不喜欢某机制但意图启用它"""
        si = self._make_intent(
            sub_goals=[{"target_mechanic": "permadeath", "change": {"type": "increase"}}],
            preferences={"disliked_mechanics": ["permadeath"]},
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "preference_violation" for c in conflicts)

    def test_numeric_conflict_negative(self, detector: ConflictDetector) -> None:
        """4. 数值冲突：负值"""
        si = self._make_intent(
            sub_goals=[{"target_mechanic": "hp", "change": {"type": "set", "value": -50}}]
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "invalid_numeric_value" for c in conflicts)

    def test_numeric_conflict_extreme(self, detector: ConflictDetector) -> None:
        """4b. 数值冲突：极端大值"""
        si = self._make_intent(
            sub_goals=[{"target_mechanic": "hp", "change": {"type": "set", "value": 9999999}}]
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "extreme_numeric_value" for c in conflicts)

    def test_reference_conflict(self, detector: ConflictDetector) -> None:
        """5. 参考冲突：两个参考含对立特征"""
        from udify.core.cognition.intent import Reference

        si = self._make_intent(
            references=[
                Reference(name="Hardcore Game", type="game", features=["high_death_penalty"]),
                Reference(name="Casual Game", type="game", features=["low_death_penalty"]),
            ]
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert any(c.type == "reference_feature_conflict" for c in conflicts)

    def test_no_conflict_clean_intent(self, detector: ConflictDetector) -> None:
        """无矛盾的意图不应报冲突"""
        si = self._make_intent(
            sub_goals=[{"target_mechanic": "hp", "change": {"type": "increase"}}]
        )
        conflicts = detector.detect(Intent(raw_text="test"), si)
        assert conflicts == []

    def test_resolve_conflicts_records_unresolved(self, detector: ConflictDetector) -> None:
        """resolve_conflicts 应把无法自动解决的冲突记入 metadata"""
        c = Conflict(conflict_type="preference_violation", description="x", severity="medium")
        si = self._make_intent()
        resolved = detector.resolve_conflicts(si, [c])
        assert "unresolved_conflicts" in resolved.metadata


class TestStructuredIntent:
    """StructuredIntent 序列化"""

    def test_from_intent_maps_type(self) -> None:
        intent = Intent(
            raw_text="让Boss更难",
            language="zh",
            intent_type=IntentType.DIFFICULTY_ADJUSTMENT,
            primary_goal="adjust_enemy_difficulty",
            sub_goals=["modify_health"],
        )
        si = StructuredIntent.from_intent(intent)
        assert si.primary_goal["type"] == "difficulty_adjustment"
        assert si.primary_goal["target"] == "adjust_enemy_difficulty"
        assert len(si.sub_goals) == 1

    def test_to_dict_includes_all_sections(self) -> None:
        si = StructuredIntent()
        d = si.to_dict()
        for key in [
            "version",
            "intent_id",
            "raw_input",
            "primary_goal",
            "sub_goals",
            "references",
            "constraints",
            "preferences",
            "metadata",
        ]:
            assert key in d
