"""
SQLite JobStore（ORCH-JOB-05 + OBS-01，2026-08 批次 4A）。

ADR-v3-006：stdlib sqlite3（WAL）+ 文件工件，零新依赖，本地模式红线。
- ``jobs`` 表：当前状态快照（可重建自事件流，但快照查询更省）。
- ``job_events`` 表：append-only 事件流 + 链式哈希（ORCH-JOB-04 审计链，
  哈希方案与 tool_gateway.audit.ToolAuditChain 一致：
  ``record_hash = sha256(prev_hash + canonical(fields))``）。
  该表同时就是 OBS-01 的 trace schema——API 时间线直接读它，一份数据两用。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from udify.core.orchestration.mod_job import JobError, JobStatus, ModJob

_SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    game_root TEXT NOT NULL,
    intent TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    artifacts_dir TEXT NOT NULL,
    error_json TEXT,
    checkpoint_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS job_events (
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    stage TEXT NOT NULL,
    event TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    PRIMARY KEY (job_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs (created_at DESC);
"""


@dataclass(frozen=True)
class JobEvent:
    """一条 job 事件（trace + 审计双用途）。"""

    job_id: str
    seq: int
    ts: float
    stage: str
    event: str
    payload: dict[str, Any]
    prev_hash: str
    record_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "seq": self.seq,
            "ts": self.ts,
            "stage": self.stage,
            "event": self.event,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }


def _event_hash(
    job_id: str, seq: int, ts: float, stage: str, event: str, payload: dict[str, Any], prev: str
) -> str:
    canonical = json.dumps(
        {
            "job_id": job_id,
            "seq": seq,
            "ts": ts,
            "stage": stage,
            "event": event,
            "payload": payload,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256((prev + canonical).encode()).hexdigest()


class JobStore:
    """ModJob 的 durable 存储（进程内线程安全）。

    # ponytail: 一把全局写锁 + WAL，单机单进程（uvicorn 单 worker）足够；
    # 多进程/多机时升级为服务化存储，届时幂等键 (job_id, seq) 已预留。
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,)
                )
            elif row[0] != _SCHEMA_VERSION:
                raise RuntimeError(
                    f"job store schema version mismatch: db={row[0]} code={_SCHEMA_VERSION}"
                )

    # ------------------------------------------------------------------ jobs

    def save(self, job: ModJob) -> None:
        """插入或整行覆盖 job 快照。"""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs (job_id, game_root, intent, status, created_at,
                                  updated_at, artifacts_dir, error_json, checkpoint_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    error_json=excluded.error_json,
                    checkpoint_json=excluded.checkpoint_json
                """,
                (
                    job.job_id,
                    job.game_root,
                    job.intent,
                    job.status.value,
                    job.created_at,
                    job.updated_at,
                    job.artifacts_dir,
                    json.dumps(job.error.to_dict()) if job.error else None,
                    json.dumps(job.checkpoint, default=str),
                ),
            )

    def get(self, job_id: str) -> ModJob | None:
        row = self._conn.execute(
            "SELECT job_id, game_root, intent, status, created_at, updated_at,"
            " artifacts_dir, error_json, checkpoint_json FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self, limit: int = 50, offset: int = 0) -> list[ModJob]:
        rows = self._conn.execute(
            "SELECT job_id, game_root, intent, status, created_at, updated_at,"
            " artifacts_dir, error_json, checkpoint_json FROM jobs"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def list_by_status(self, statuses: frozenset[JobStatus]) -> list[ModJob]:
        placeholders = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT job_id, game_root, intent, status, created_at, updated_at,"
            f" artifacts_dir, error_json, checkpoint_json FROM jobs"
            f" WHERE status IN ({placeholders}) ORDER BY created_at",
            tuple(s.value for s in statuses),
        ).fetchall()
        return [self._row_to_job(r) for r in rows]

    @staticmethod
    def _row_to_job(row: tuple[Any, ...]) -> ModJob:
        return ModJob(
            job_id=row[0],
            game_root=row[1],
            intent=row[2],
            status=JobStatus(row[3]),
            created_at=row[4],
            updated_at=row[5],
            artifacts_dir=row[6],
            error=JobError.from_dict(json.loads(row[7])) if row[7] else None,
            checkpoint=json.loads(row[8]) if row[8] else {},
        )

    # ---------------------------------------------------------------- events

    def append_event(
        self, job_id: str, stage: str, event: str, payload: dict[str, Any] | None = None
    ) -> JobEvent:
        """追加一条链式哈希事件（审计 + trace）。"""
        payload = payload or {}
        ts = time.time()
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT seq, record_hash FROM job_events WHERE job_id = ?"
                " ORDER BY seq DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            seq = (row[0] + 1) if row else 1
            prev = row[1] if row else ""
            record_hash = _event_hash(job_id, seq, ts, stage, event, payload, prev)
            self._conn.execute(
                "INSERT INTO job_events (job_id, seq, ts, stage, event, payload_json,"
                " prev_hash, record_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job_id,
                    seq,
                    ts,
                    stage,
                    event,
                    json.dumps(payload, default=str),
                    prev,
                    record_hash,
                ),
            )
        return JobEvent(job_id, seq, ts, stage, event, payload, prev, record_hash)

    def events(self, job_id: str, after_seq: int = 0) -> list[JobEvent]:
        rows = self._conn.execute(
            "SELECT job_id, seq, ts, stage, event, payload_json, prev_hash, record_hash"
            " FROM job_events WHERE job_id = ? AND seq > ? ORDER BY seq",
            (job_id, after_seq),
        ).fetchall()
        return [JobEvent(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]), r[6], r[7]) for r in rows]

    def verify_chain(self, job_id: str) -> bool:
        """校验事件链完整性（ORCH-JOB-04：篡改任意一条即断裂）。"""
        prev = ""
        for ev in self.events(job_id):
            if ev.prev_hash != prev:
                return False
            if _event_hash(ev.job_id, ev.seq, ev.ts, ev.stage, ev.event, ev.payload, prev) != (
                ev.record_hash
            ):
                return False
            prev = ev.record_hash
        return True

    # ------------------------------------------------------------ transition

    def transition(
        self,
        job: ModJob,
        target: JobStatus,
        *,
        event: str,
        payload: dict[str, Any] | None = None,
        error: JobError | None = None,
        checkpoint_update: dict[str, Any] | None = None,
    ) -> ModJob:
        """状态迁移 + 快照落库 + 事件追加（同一把锁内，原子）。"""
        new_job = job.with_status(target, error=error, checkpoint_update=checkpoint_update)
        merged_payload = dict(payload or {})
        merged_payload["from"] = job.status.value
        merged_payload["to"] = target.value
        if error is not None:
            merged_payload["error"] = error.to_dict()
        self.save(new_job)
        self.append_event(job.job_id, stage=target.value, event=event, payload=merged_payload)
        return new_job

    def close(self) -> None:
        self._conn.close()


__all__ = ["JobEvent", "JobStore"]
