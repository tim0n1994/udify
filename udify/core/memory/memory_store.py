"""
Udify Memory System

记忆系统：持久化用户偏好、意图模板、执行历史、知识库。
支持向量检索（基于 numpy 的简化版）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class IntentTemplate:
    """意图模板"""
    template_id: str
    pattern: str  # 正则或关键词模式
    description: str
    target_types: List[str]  # 影响的节点类型
    typical_actions: List[str]  # 典型操作序列
    success_rate: float = 0.0
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class UserPreference:
    """用户偏好"""
    user_id: str
    preservative_bias: float = 0.7  # 保守倾向
    difficulty_preference: str = "normal"  # easy, normal, hard
    favorite_mod_types: List[str] = field(default_factory=list)
    disliked_patterns: List[str] = field(default_factory=list)
    preferred_budget: float = 0.5
    last_session_id: Optional[str] = None


@dataclass
class ExecutionRecord:
    """执行记录"""
    record_id: str
    session_id: str
    intent: str
    patch_id: str
    operations_count: int
    success: bool
    user_rating: Optional[int] = None
    execution_time: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class MemoryStore:
    """
    记忆存储

    使用 JSON 文件持久化，支持向量检索的简化版。
    """

    def __init__(self, base_dir: Path = Path(".udify/memory")) -> None:
        self.base_dir = base_dir
        self.templates_file = base_dir / "intent_templates.json"
        self.preferences_file = base_dir / "user_preferences.json"
        self.history_file = base_dir / "execution_history.json"
        self.knowledge_file = base_dir / "knowledge_base.json"

        self.base_dir.mkdir(parents=True, exist_ok=True)

        self._templates: Dict[str, IntentTemplate] = {}
        self._preferences: Dict[str, UserPreference] = {}
        self._history: List[ExecutionRecord] = []
        self._knowledge: Dict[str, Any] = {}

        self._load_all()

    def _load_all(self) -> None:
        """加载所有数据"""
        if self.templates_file.exists():
            data = json.loads(self.templates_file.read_text(encoding="utf-8"))
            for item in data:
                self._templates[item["template_id"]] = IntentTemplate(**item)

        if self.preferences_file.exists():
            data = json.loads(self.preferences_file.read_text(encoding="utf-8"))
            for uid, item in data.items():
                self._preferences[uid] = UserPreference(**item)

        if self.history_file.exists():
            data = json.loads(self.history_file.read_text(encoding="utf-8"))
            self._history = [ExecutionRecord(**item) for item in data]

        if self.knowledge_file.exists():
            self._knowledge = json.loads(self.knowledge_file.read_text(encoding="utf-8"))

    def _save_all(self) -> None:
        """保存所有数据"""
        self.templates_file.write_text(
            json.dumps([t.__dict__ for t in self._templates.values()], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.preferences_file.write_text(
            json.dumps({uid: p.__dict__ for uid, p in self._preferences.items()}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.history_file.write_text(
            json.dumps([r.__dict__ for r in self._history], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.knowledge_file.write_text(
            json.dumps(self._knowledge, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_template(self, template: IntentTemplate) -> None:
        """添加意图模板"""
        self._templates[template.template_id] = template
        self._save_all()

    def find_matching_templates(self, intent: str, top_k: int = 3) -> List[IntentTemplate]:
        """查找匹配的意图模板（简化版：关键词匹配）"""
        intent_lower = intent.lower()
        scores = []

        for template in self._templates.values():
            score = 0.0
            pattern_lower = template.pattern.lower()

            # 直接包含
            if pattern_lower in intent_lower:
                score += 2.0

            # 关键词重叠
            pattern_words = set(pattern_lower.split())
            intent_words = set(intent_lower.split())
            overlap = len(pattern_words & intent_words)
            score += overlap / max(len(pattern_words), 1)

            # 成功率加权
            score += template.success_rate * 0.5

            if score > 0.3:
                scores.append((template, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [t[0] for t in scores[:top_k]]

    def get_or_create_preference(self, user_id: str) -> UserPreference:
        """获取或创建用户偏好"""
        if user_id not in self._preferences:
            self._preferences[user_id] = UserPreference(user_id=user_id)
            self._save_all()
        return self._preferences[user_id]

    def update_preference(self, preference: UserPreference) -> None:
        """更新用户偏好"""
        self._preferences[preference.user_id] = preference
        self._save_all()

    def add_execution_record(self, record: ExecutionRecord) -> None:
        """添加执行记录"""
        self._history.append(record)
        # 限制历史大小
        if len(self._history) > 10000:
            self._history = self._history[-10000:]
        self._save_all()

    def get_user_history(self, user_id: str, limit: int = 50) -> List[ExecutionRecord]:
        """获取用户执行历史"""
        records = [r for r in self._history if r.session_id.startswith(user_id)]
        return records[-limit:]

    def get_similar_executions(self, intent: str, limit: int = 5) -> List[ExecutionRecord]:
        """获取相似意图的执行记录"""
        intent_lower = intent.lower()
        intent_words = set(intent_lower.split())

        scored = []
        for record in self._history:
            record_words = set(record.intent.lower().split())
            overlap = len(intent_words & record_words)
            if overlap > 0:
                score = overlap / max(len(intent_words), len(record_words))
                if record.success:
                    score += 0.3
                if record.user_rating and record.user_rating >= 4:
                    score += 0.2
                scored.append((record, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in scored[:limit]]

    def get_successful_patterns(self, min_rating: int = 4, limit: int = 20) -> List[Dict[str, Any]]:
        """获取成功的模式"""
        successful = [
            {
                "intent": r.intent,
                "operations_count": r.operations_count,
                "rating": r.user_rating,
            }
            for r in self._history
            if r.success and r.user_rating and r.user_rating >= min_rating
        ]
        return successful[:limit]

    def update_knowledge(self, key: str, value: Any) -> None:
        """更新知识库"""
        self._knowledge[key] = value
        self._save_all()

    def get_knowledge(self, key: str, default: Any = None) -> Any:
        """获取知识"""
        return self._knowledge.get(key, default)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "templates": len(self._templates),
            "users": len(self._preferences),
            "history": len(self._history),
            "successful": sum(1 for r in self._history if r.success),
            "knowledge_keys": len(self._knowledge),
        }


class MemoryEnricher:
    """
    记忆富化器

    从执行结果中提取知识，更新记忆存储。
    """

    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    def enrich_from_patch(self, intent: str, patch: Any, success: bool, rating: Optional[int] = None) -> None:
        """从 Patch 中提取模板"""
        # 生成模板 ID
        template_id = hashlib.sha256(intent.encode()).hexdigest()[:16]

        # 提取操作类型
        action_types = []
        if hasattr(patch, "operations"):
            action_types = list(set(op.op_type.name for op in patch.operations))

        # 更新或创建模板
        existing = self.store._templates.get(template_id)
        if existing:
            existing.usage_count += 1
            if success:
                existing.success_rate = (existing.success_rate * (existing.usage_count - 1) + 1.0) / existing.usage_count
            else:
                existing.success_rate = (existing.success_rate * (existing.usage_count - 1)) / existing.usage_count
        else:
            template = IntentTemplate(
                template_id=template_id,
                pattern=intent[:50],
                description=intent,
                target_types=[],
                typical_actions=action_types,
                success_rate=1.0 if success else 0.0,
                usage_count=1,
            )
            self.store.add_template(template)

    def enrich_from_feedback(self, user_id: str, intent: str, feedback: str, rating: int) -> None:
        """从反馈中更新用户偏好"""
        pref = self.store.get_or_create_preference(user_id)

        # 根据评分调整保守倾向
        if rating >= 4:
            pref.preservative_bias = min(1.0, pref.preservative_bias + 0.02)
        elif rating <= 2:
            pref.preservative_bias = max(0.0, pref.preservative_bias - 0.05)

        # 记录不喜欢的模式
        if rating <= 2:
            pref.disliked_patterns.append(intent[:30])
            if len(pref.disliked_patterns) > 50:
                pref.disliked_patterns = pref.disliked_patterns[-50:]

        self.store.update_preference(pref)
