"""
Udify Session Manager

会话管理：跟踪一次完整的魔改会话生命周期。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from udify.models.content_graph import ContentGraph
from udify.models.cdl_patch import CDLPatch, PatchOperation


class SessionStatus(Enum):
    """会话状态"""
    CREATED = auto()
    PERCEIVING = auto()
    PLANNING = auto()
    EXECUTING = auto()
    VALIDATING = auto()
    COMPLETED = auto()
    FAILED = auto()
    ROLLED_BACK = auto()


@dataclass
class SessionCheckpoint:
    """会话检查点"""
    name: str
    graph_snapshot: ContentGraph
    operations_applied: List[PatchOperation]
    timestamp: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))


@dataclass
class ModSession:
    """
    魔改会话

    包含一次完整魔改过程的所有状态：
    - 意图历史
    - 图谱快照
    - Patch 历史
    - 用户反馈
    - 检查点
    """
    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "anonymous"
    game_id: str = ""
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))
    updated_at: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))

    # 意图
    intents: List[str] = field(default_factory=list)
    current_intent: str = ""

    # 图谱
    original_graph: Optional[ContentGraph] = None
    current_graph: Optional[ContentGraph] = None

    # Patch 历史
    patches: List[CDLPatch] = field(default_factory=list)
    applied_operations: List[PatchOperation] = field(default_factory=list)

    # 检查点
    checkpoints: List[SessionCheckpoint] = field(default_factory=list)

    # 用户反馈
    feedback_history: List[Dict[str, Any]] = field(default_factory=list)

    # 成本追踪
    cost_spent: float = 0.0
    llm_calls: int = 0

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_intent(self, intent: str) -> None:
        """添加意图"""
        self.intents.append(intent)
        self.current_intent = intent
        self._touch()

    def set_graph(self, graph: ContentGraph) -> None:
        """设置当前图谱"""
        if self.original_graph is None:
            self.original_graph = deepcopy(graph)
        self.current_graph = graph
        self._touch()

    def add_patch(self, patch: CDLPatch) -> None:
        """添加 Patch"""
        self.patches.append(patch)
        self.applied_operations.extend(patch.operations)
        self._touch()

    def create_checkpoint(self, name: str) -> SessionCheckpoint:
        """创建检查点"""
        if self.current_graph is None:
            raise ValueError("No graph to checkpoint")

        checkpoint = SessionCheckpoint(
            name=name,
            graph_snapshot=deepcopy(self.current_graph),
            operations_applied=list(self.applied_operations),
        )
        self.checkpoints.append(checkpoint)
        return checkpoint

    def rollback_to_checkpoint(self, checkpoint_name: str) -> bool:
        """回滚到指定检查点"""
        for cp in reversed(self.checkpoints):
            if cp.name == checkpoint_name:
                self.current_graph = deepcopy(cp.graph_snapshot)
                self.applied_operations = list(cp.operations_applied)
                self.status = SessionStatus.ROLLED_BACK
                self._touch()
                return True
        return False

    def rollback_to_last(self) -> bool:
        """回滚到最后一个检查点"""
        if not self.checkpoints:
            return False
        return self.rollback_to_checkpoint(self.checkpoints[-1].name)

    def add_feedback(self, feedback: str, rating: Optional[int] = None) -> None:
        """添加用户反馈"""
        self.feedback_history.append({
            "feedback": feedback,
            "rating": rating,
            "timestamp": datetime.now().replace(tzinfo=None).isoformat(),
            "intent": self.current_intent,
        })
        self._touch()

    def record_cost(self, cost: float, llm_call: bool = False) -> None:
        """记录成本"""
        self.cost_spent += cost
        if llm_call:
            self.llm_calls += 1
        self._touch()

    def set_status(self, status: SessionStatus) -> None:
        """设置状态"""
        self.status = status
        self._touch()

    def _touch(self) -> None:
        """更新时间戳"""
        self.updated_at = datetime.now().replace(tzinfo=None)

    def summary(self) -> str:
        """生成会话摘要"""
        lines = [
            f"Session[{self.session_id[:8]}] - {self.status.name}",
            f"  Game: {self.game_id}",
            f"  Intents: {len(self.intents)}",
            f"  Patches: {len(self.patches)} ({sum(len(p.operations) for p in self.patches)} ops)",
            f"  Checkpoints: {len(self.checkpoints)}",
            f"  Cost: ${self.cost_spent:.4f} ({self.llm_calls} LLM calls)",
            f"  Feedback: {len(self.feedback_history)}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "game_id": self.game_id,
            "status": self.status.name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "intents": self.intents,
            "current_intent": self.current_intent,
            "patch_count": len(self.patches),
            "operation_count": len(self.applied_operations),
            "checkpoint_count": len(self.checkpoints),
            "cost_spent": self.cost_spent,
            "llm_calls": self.llm_calls,
            "feedback_count": len(self.feedback_history),
        }


class SessionManager:
    """
    会话管理器

    管理所有活跃的魔改会话。
    """

    def __init__(self, max_sessions: int = 100) -> None:
        self._sessions: Dict[str, ModSession] = {}
        self._user_sessions: Dict[str, List[str]] = {}
        self._max_sessions = max_sessions

    def create_session(self, user_id: str, game_id: str) -> ModSession:
        """创建新会话"""
        # 清理过期会话
        self._cleanup_old_sessions()

        session = ModSession(user_id=user_id, game_id=game_id)
        self._sessions[session.session_id] = session
        self._user_sessions.setdefault(user_id, []).append(session.session_id)

        return session

    def get_session(self, session_id: str) -> Optional[ModSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """关闭会话"""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.set_status(SessionStatus.COMPLETED)
        return True

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        session = self._sessions.get(session_id)
        if session is None:
            return False

        del self._sessions[session_id]

        user_id = session.user_id
        if user_id in self._user_sessions:
            self._user_sessions[user_id] = [
                sid for sid in self._user_sessions[user_id] if sid != session_id
            ]

        return True

    def get_user_sessions(self, user_id: str) -> List[ModSession]:
        """获取用户的所有会话"""
        session_ids = self._user_sessions.get(user_id, [])
        return [self._sessions[sid] for sid in session_ids if sid in self._sessions]

    def get_active_sessions(self) -> List[ModSession]:
        """获取活跃会话"""
        return [
            s for s in self._sessions.values()
            if s.status not in [SessionStatus.COMPLETED, SessionStatus.FAILED]
        ]

    def _cleanup_old_sessions(self) -> None:
        """清理最旧的会话"""
        while len(self._sessions) >= self._max_sessions:
            # 找到最旧的已完成会话
            old_sessions = [
                (sid, s) for sid, s in self._sessions.items()
                if s.status in [SessionStatus.COMPLETED, SessionStatus.FAILED]
            ]

            if not old_sessions:
                # 如果没有已完成的，删除最旧的
                old_sessions = sorted(
                    self._sessions.items(),
                    key=lambda x: x[1].created_at,
                )

            if old_sessions:
                oldest_id = old_sessions[0][0]
                self.delete_session(oldest_id)
            else:
                break

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        statuses: Dict[str, int] = {}
        for s in self._sessions.values():
            name = s.status.name
            statuses[name] = statuses.get(name, 0) + 1

        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len(self.get_active_sessions()),
            "status_breakdown": statuses,
            "total_cost": sum(s.cost_spent for s in self._sessions.values()),
            "total_llm_calls": sum(s.llm_calls for s in self._sessions.values()),
        }
