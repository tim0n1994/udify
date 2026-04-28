"""
Udify Feedback - Feedback Loop

反馈闭环：收集用户反馈，学习优化，持续改进规划质量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UserFeedback:
    """用户反馈"""
    feedback_id: str
    session_id: str
    mod_id: str
    feedback_type: str  # rating, comment, rejection, acceptance
    content: str
    rating: Optional[int] = None  # 1-5
    timestamp: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModPattern:
    """魔改模式"""
    pattern_id: str
    intent_keywords: List[str]
    action_sequence: List[str]
    target_properties: List[str]
    success_rate: float = 0.0
    usage_count: int = 0
    average_rating: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))


@dataclass
class ActionWeight:
    """动作权重"""
    action_type: str
    target_type: str
    weight: float = 1.0
    success_count: int = 0
    failure_count: int = 0
    average_rating: float = 0.0
    usage_count: int = 0


class FeedbackStore:
    """反馈存储"""

    def __init__(self) -> None:
        self._feedbacks: Dict[str, UserFeedback] = {}
        self._session_feedbacks: Dict[str, List[str]] = {}
        self._mod_feedbacks: Dict[str, List[str]] = {}

    def save(self, feedback: UserFeedback) -> None:
        """保存反馈"""
        self._feedbacks[feedback.feedback_id] = feedback
        self._session_feedbacks.setdefault(feedback.session_id, []).append(feedback.feedback_id)
        self._mod_feedbacks.setdefault(feedback.mod_id, []).append(feedback.feedback_id)

    def get_session_feedback(self, session_id: str) -> List[UserFeedback]:
        """获取会话反馈"""
        ids = self._session_feedbacks.get(session_id, [])
        return [self._feedbacks[i] for i in ids if i in self._feedbacks]

    def get_mod_feedback(self, mod_id: str) -> List[UserFeedback]:
        """获取 Mod 反馈"""
        ids = self._mod_feedbacks.get(mod_id, [])
        return [self._feedbacks[i] for i in ids if i in self._feedbacks]

    def get_all_feedback(self) -> List[UserFeedback]:
        """获取所有反馈"""
        return list(self._feedbacks.values())


class LearningEngine:
    """
    学习引擎

    从反馈中学习，优化规划策略。
    """

    def __init__(self) -> None:
        self._patterns: Dict[str, ModPattern] = {}
        self._action_weights: Dict[str, ActionWeight] = {}
        self._feedback_store = FeedbackStore()

    async def analyze_sentiment(self, comment: str) -> float:
        """
        分析反馈情感

        返回 -1.0 (负面) 到 1.0 (正面)
        """
        # 简化版：基于关键词的情感分析
        positive_words = ["好", "棒", "优秀", "完美", "喜欢", "满意", "great", "good", "excellent", "perfect", "like", "love", "nice"]
        negative_words = ["差", "糟", "垃圾", "失败", "讨厌", "不满", "bad", "terrible", "awful", "worst", "hate", "dislike", "poor"]

        comment_lower = comment.lower()
        positive_count = sum(1 for w in positive_words if w in comment_lower)
        negative_count = sum(1 for w in negative_words if w in comment_lower)

        total = positive_count + negative_count
        if total == 0:
            return 0.0

        return (positive_count - negative_count) / total

    async def update_action_weight(
        self,
        action_type: str,
        target_type: str,
        sentiment: float,
        rating: Optional[int] = None,
    ) -> None:
        """更新动作权重"""
        key = f"{action_type}:{target_type}"

        if key not in self._action_weights:
            self._action_weights[key] = ActionWeight(
                action_type=action_type,
                target_type=target_type,
            )

        weight = self._action_weights[key]

        # 基于情感更新权重
        if sentiment > 0.3:
            weight.weight = min(2.0, weight.weight * 1.1)
            weight.success_count += 1
        elif sentiment < -0.3:
            weight.weight = max(0.1, weight.weight * 0.9)
            weight.failure_count += 1

        # 基于评分更新
        if rating is not None:
            weight.average_rating = (
                weight.average_rating * weight.usage_count + rating
            ) / (weight.usage_count + 1)

        weight.usage_count += 1

    async def learn_successful_pattern(self, patch: Any, rating: int) -> Optional[ModPattern]:
        """从成功的 Patch 中学习模式"""
        if rating < 4:
            return None

        # 提取模式
        intent_keywords = self._extract_keywords(patch.intent)
        action_sequence = [op.op_type.name for op in patch.operations]
        target_properties = self._extract_target_properties(patch)

        pattern_id = hash(f"{intent_keywords}:{action_sequence}")

        if pattern_id in self._patterns:
            # 更新现有模式
            pattern = self._patterns[pattern_id]
            pattern.usage_count += 1
            pattern.average_rating = (
                pattern.average_rating * (pattern.usage_count - 1) + rating
            ) / pattern.usage_count
            pattern.success_rate = pattern.average_rating / 5.0
        else:
            # 创建新模式
            pattern = ModPattern(
                pattern_id=str(pattern_id),
                intent_keywords=intent_keywords,
                action_sequence=action_sequence,
                target_properties=target_properties,
                success_rate=rating / 5.0,
                usage_count=1,
                average_rating=float(rating),
            )
            self._patterns[pattern_id] = pattern

        return pattern

    async def find_similar_patterns(self, intent_keywords: List[str]) -> List[ModPattern]:
        """查找相似的模式"""
        scored_patterns = []

        for pattern in self._patterns.values():
            # 计算关键词重叠度
            overlap = len(set(intent_keywords) & set(pattern.intent_keywords))
            score = overlap / max(len(intent_keywords), len(pattern.intent_keywords))

            # 加权成功率和评分
            final_score = score * pattern.success_rate * (pattern.average_rating / 5.0)

            if score > 0.3:  # 至少 30% 重叠
                scored_patterns.append((pattern, final_score))

        # 按分数排序
        scored_patterns.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in scored_patterns[:5]]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        import re

        # 分词（简化版）
        words = re.findall(r"\b\w+\b", text.lower())

        # 过滤停用词
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while"}

        return [w for w in words if w not in stopwords and len(w) > 2]

    def _extract_target_properties(self, patch: Any) -> List[str]:
        """提取目标属性"""
        properties = []
        for op in patch.operations:
            if hasattr(op, "payload") and "key" in op.payload:
                properties.append(op.payload["key"])
        return properties

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "pattern_count": len(self._patterns),
            "action_weight_count": len(self._action_weights),
            "feedback_count": len(self._feedback_store._feedbacks),
            "average_pattern_success": (
                sum(p.success_rate for p in self._patterns.values()) / len(self._patterns)
                if self._patterns else 0
            ),
            "top_patterns": sorted(
                self._patterns.values(),
                key=lambda p: p.success_rate * p.average_rating,
                reverse=True,
            )[:10],
        }


class FeedbackLoop:
    """
    反馈闭环

    完整流程：
    收集反馈 → 情感分析 → 归因分析 → 模式学习 → 权重更新
    """

    def __init__(self) -> None:
        self.feedback_store = FeedbackStore()
        self.learning_engine = LearningEngine()

    async def collect_feedback(
        self,
        session_id: str,
        mod_id: str,
        feedback_type: str,
        content: str,
        rating: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UserFeedback:
        """收集用户反馈"""
        import hashlib

        feedback_id = hashlib.sha256(
            f"{session_id}:{mod_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        feedback = UserFeedback(
            feedback_id=feedback_id,
            session_id=session_id,
            mod_id=mod_id,
            feedback_type=feedback_type,
            content=content,
            rating=rating,
            metadata=metadata or {},
        )

        self.feedback_store.save(feedback)

        # 实时分析
        await self._analyze_feedback(feedback)

        return feedback

    async def _analyze_feedback(self, feedback: UserFeedback) -> None:
        """分析反馈"""
        # 1. 情感分析
        sentiment = await self.learning_engine.analyze_sentiment(feedback.content)

        # 2. 归因分析（如果有 Patch 信息）
        if "patch" in feedback.metadata:
            patch = feedback.metadata["patch"]

            # 更新每个操作的权重
            for op in patch.operations:
                await self.learning_engine.update_action_weight(
                    action_type=op.op_type.name,
                    target_type=op.target_id.split("_")[0] if "_" in op.target_id else "unknown",
                    sentiment=sentiment,
                    rating=feedback.rating,
                )

            # 3. 模式学习（高评分）
            if feedback.rating and feedback.rating >= 4:
                await self.learning_engine.learn_successful_pattern(
                    patch, feedback.rating
                )

    async def get_suggestions(self, intent: str) -> List[Dict[str, Any]]:
        """基于历史反馈获取建议"""
        keywords = self.learning_engine._extract_keywords(intent)
        patterns = await self.learning_engine.find_similar_patterns(keywords)

        suggestions = []
        for pattern in patterns[:3]:
            suggestions.append({
                "pattern_id": pattern.pattern_id,
                "keywords": pattern.intent_keywords,
                "success_rate": pattern.success_rate,
                "average_rating": pattern.average_rating,
                "usage_count": pattern.usage_count,
                "description": f"基于 {pattern.usage_count} 次成功使用的模式，成功率 {pattern.success_rate:.1%}",
            })

        return suggestions

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "feedback": {
                "total": len(self.feedback_store._feedbacks),
                "by_type": self._count_by_type(),
            },
            "learning": self.learning_engine.get_stats(),
        }

    def _count_by_type(self) -> Dict[str, int]:
        """按类型统计反馈"""
        counts = {}
        for f in self.feedback_store._feedbacks.values():
            counts[f.feedback_type] = counts.get(f.feedback_type, 0) + 1
        return counts
