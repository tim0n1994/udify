"""
Udify Infrastructure - Event Bus

事件驱动架构核心组件，解耦各层通信。
支持异步事件发射、订阅和观察者模式。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Coroutine, Dict, List, Optional


class EventType(Enum):
    """核心事件类型"""
    # 意图层事件
    INTENT_RECEIVED = auto()
    INTENT_PARSED = auto()
    INTENT_REJECTED = auto()

    # 感知层事件
    PERCEPTION_STARTED = auto()
    PERCEPTION_COMPLETED = auto()
    PERCEPTION_FAILED = auto()
    GRAPH_UPDATED = auto()
    GRAPH_INVALIDATED = auto()

    # 规划层事件
    PLANNING_STARTED = auto()
    PLANNING_COMPLETED = auto()
    PLANNING_FAILED = auto()

    # 补丁层事件
    PATCH_VALIDATED = auto()
    PATCH_REJECTED = auto()

    # 执行层事件
    EXECUTION_STARTED = auto()
    EXECUTION_COMPLETED = auto()
    EXECUTION_FAILED = auto()
    MOD_CREATED = auto()

    # 验证层事件
    VALIDATION_PASSED = auto()
    VALIDATION_FAILED = auto()

    # 用户反馈事件
    USER_FEEDBACK = auto()
    USER_CONFIRMED = auto()
    USER_CANCELLED = auto()

    # 系统事件
    SESSION_CREATED = auto()
    SESSION_CLOSED = auto()
    COST_LIMIT_REACHED = auto()
    SANDBOX_VIOLATION = auto()


@dataclass
class Event:
    """事件对象"""
    event_type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now().replace(tzinfo=None))
    task_id: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.name,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "session_id": self.session_id,
        }


EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


class EventBus:
    """
    事件总线

    支持:
    - 异步事件发射
    - 多订阅者
    - 事件历史记录
    - 错误隔离（一个处理器失败不影响其他）
    """

    def __init__(self, max_history: int = 10000) -> None:
        self._subscribers: Dict[EventType, List[EventHandler]] = {}
        self._history: List[Event] = []
        self._max_history = max_history
        self._event_count = 0

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """订阅事件"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """取消订阅"""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def emit(self, event: Event) -> None:
        """异步发射事件"""
        self._event_count += 1
        self._history.append(event)

        # 限制历史大小
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._subscribers.get(event.event_type, [])

        # 并行执行所有处理器，错误隔离
        tasks = []
        for handler in handlers:
            tasks.append(self._safe_handle(handler, event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_handle(self, handler: EventHandler, event: Event) -> None:
        """安全执行处理器，隔离错误"""
        try:
            await handler(event)
        except Exception as e:
            # 错误不影响其他处理器
            print(f"Event handler error for {event.event_type.name}: {e}")

    def get_history(
        self,
        event_type: Optional[EventType] = None,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """查询事件历史"""
        results = self._history

        if event_type:
            results = [e for e in results if e.event_type == event_type]

        if session_id:
            results = [e for e in results if e.session_id == session_id]

        return results[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取事件统计"""
        stats = {et.name: 0 for et in EventType}
        for event in self._history:
            stats[event.event_type.name] += 1
        return {
            "total_events": self._event_count,
            "history_size": len(self._history),
            "subscriber_count": sum(len(hs) for hs in self._subscribers.values()),
            "event_breakdown": stats,
        }


# 便捷函数
async def emit_event(
    bus: EventBus,
    event_type: EventType,
    payload: Dict[str, Any],
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """便捷发射事件"""
    event = Event(
        event_type=event_type,
        payload=payload,
        task_id=task_id,
        session_id=session_id,
    )
    await bus.emit(event)
