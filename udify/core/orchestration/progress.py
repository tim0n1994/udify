"""
流式任务进度事件（iter4 M4，T4-STREAMING-UX 研究落地）。

ProgressEvent 从 JobRunner 的步进调用产生，记录阶段内进度（perceive 扫描到第 N 文件、
plan 搜索第 K 步等）。progress_store 持久化到 SQLite（崩溃可恢复）。
CancellationToken 支持「用户中途取消」的端到端语义。

设计原则（T4 研究结论）：
- 纯数据（frozen），可序列化，无网络副作用。
- 进度是「best-effort 观测」，不影响状态机正确性。
- 取消是协作式（cooperative）：JobRunner 在安全点检查 token，不强制 kill。
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ProgressStage(StrEnum):
    """与 JobStatus 对齐的阶段。"""

    PERCEIVING = "perceiving"
    PLANNING = "planning"
    APPLYING = "applying"
    VALIDATING = "validating"
    PACKAGING = "packaging"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """单个进度事件。"""

    job_id: str
    stage: ProgressStage
    detail: str = ""
    pct: float = 0.0  # 0-100
    current: int = 0
    total: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    seq: int = 0

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "stage": self.stage.value,
            "detail": self.detail,
            "pct": self.pct,
            "current": self.current,
            "total": self.total,
            "timestamp": self.timestamp,
            "seq": self.seq,
        }


class CancellationToken:
    """协作式取消令牌（threading.Event）。

    JobRunner 在安全点（步进边界）检查 is_cancelled()，若为 True 则停止并迁移状态。
    不强制 kill 线程——对无法合作的线程不承诺强制取消（T4 研究结论）。
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def clear(self) -> None:
        self._event.clear()


class ProgressEmitter:
    """进度发射器：在步进边界产生 ProgressEvent 并广播给订阅者。

    线程安全。JobRunner 持有一个实例，在 perceive/plan 等步进里调用 emit()。
    """

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self._seq = 0
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[ProgressEvent], None]] = []
        self._last: ProgressEvent | None = None

    def subscribe(self, callback: Callable[[ProgressEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[ProgressEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def emit(
        self,
        stage: ProgressStage,
        detail: str = "",
        current: int = 0,
        total: int = 0,
    ) -> ProgressEvent:
        """产生一个进度事件并广播。返回事件本身。"""
        with self._lock:
            self._seq += 1
            pct = (current / total * 100) if total > 0 else 0.0
            evt = ProgressEvent(
                job_id=self.job_id,
                stage=stage,
                detail=detail,
                pct=round(pct, 1),
                current=current,
                total=total,
                seq=self._seq,
            )
            self._last = evt
            subs = list(self._subscribers)
        for cb in subs:
            with contextlib.suppress(Exception):
                cb(evt)  # 订阅者错误不影响进度发射
        return evt

    @property
    def last(self) -> ProgressEvent | None:
        with self._lock:
            return self._last


class ProgressStore:
    """进度事件持久化（SQLite），崩溃可恢复。

    独立表 progress_events（job_id, seq, stage, detail, pct, current, total, timestamp）。
    与 job_store 的 jobs 表共用同一 sqlite 文件（可选独立 db）。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS progress_events (
                job_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                stage TEXT NOT NULL,
                detail TEXT,
                pct REAL,
                current INTEGER,
                total INTEGER,
                timestamp TEXT,
                PRIMARY KEY (job_id, seq)
            )
            """
        )
        self._conn.commit()

    def append(self, evt: ProgressEvent) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO progress_events VALUES (?,?,?,?,?,?,?,?)",
                (
                    evt.job_id,
                    evt.seq,
                    evt.stage.value,
                    evt.detail,
                    evt.pct,
                    evt.current,
                    evt.total,
                    evt.timestamp,
                ),
            )
            self._conn.commit()

    def history(self, job_id: str, after_seq: int = 0) -> list[ProgressEvent]:
        assert self._conn is not None
        with self._lock:
            cur = self._conn.execute(
                "SELECT job_id, seq, stage, detail, pct, current, total, timestamp "
                "FROM progress_events WHERE job_id=? AND seq>? ORDER BY seq",
                (job_id, after_seq),
            )
            rows = cur.fetchall()
        return [
            ProgressEvent(
                job_id=r[0],
                seq=r[1],
                stage=ProgressStage(r[2]),
                detail=r[3] or "",
                pct=r[4] or 0.0,
                current=r[5] or 0,
                total=r[6] or 0,
                timestamp=r[7] or "",
            )
            for r in rows
        ]

    def latest(self, job_id: str) -> ProgressEvent | None:
        evts = self.history(job_id)
        return evts[-1] if evts else None

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
