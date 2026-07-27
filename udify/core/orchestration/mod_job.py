"""
ModJob 状态机（ORCH-JOB-01，2026-08 批次 4A）。

对应 ITERATION-PLAN-2026-08.md §4.1：durable job 是产品化的地基——没有它，
API 无对象可轮询、前端无历史可展示、审计无链可回放。

状态图::

    created → perceiving → planning → awaiting_review → applying
        → validating → packaging → completed
    任意进行态 → failed
    awaiting_review → rejected（终态）
    completed/failed → compensating → rolled_back（终态）

设计约束：
- 不可变优先：ModJob 是 frozen dataclass，状态迁移返回新实例。
- 非法迁移必须抛错（工业契约：状态门是唯一入口，不允许"尽量迁移"）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    """ModJob 生命周期状态。"""

    CREATED = "created"
    PERCEIVING = "perceiving"
    PLANNING = "planning"
    AWAITING_REVIEW = "awaiting_review"
    APPLYING = "applying"
    VALIDATING = "validating"
    PACKAGING = "packaging"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


# 迁移表：状态门的唯一事实来源。
_PROGRESSING: frozenset[JobStatus] = frozenset(
    {
        JobStatus.CREATED,
        JobStatus.PERCEIVING,
        JobStatus.PLANNING,
        JobStatus.AWAITING_REVIEW,
        JobStatus.APPLYING,
        JobStatus.VALIDATING,
        JobStatus.PACKAGING,
    }
)

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset({JobStatus.PERCEIVING, JobStatus.FAILED}),
    JobStatus.PERCEIVING: frozenset({JobStatus.PLANNING, JobStatus.FAILED}),
    JobStatus.PLANNING: frozenset({JobStatus.AWAITING_REVIEW, JobStatus.FAILED}),
    JobStatus.AWAITING_REVIEW: frozenset(
        {JobStatus.APPLYING, JobStatus.REJECTED, JobStatus.FAILED}
    ),
    JobStatus.APPLYING: frozenset({JobStatus.VALIDATING, JobStatus.FAILED}),
    JobStatus.VALIDATING: frozenset({JobStatus.PACKAGING, JobStatus.FAILED}),
    JobStatus.PACKAGING: frozenset({JobStatus.COMPLETED, JobStatus.FAILED}),
    JobStatus.COMPLETED: frozenset({JobStatus.COMPENSATING}),
    JobStatus.FAILED: frozenset({JobStatus.COMPENSATING}),
    JobStatus.COMPENSATING: frozenset({JobStatus.ROLLED_BACK, JobStatus.FAILED}),
    JobStatus.REJECTED: frozenset(),
    JobStatus.ROLLED_BACK: frozenset(),
}

TERMINAL_STATUSES: frozenset[JobStatus] = frozenset({JobStatus.REJECTED, JobStatus.ROLLED_BACK})


class InvalidTransitionError(Exception):
    """非法状态迁移。code 遵循 DOMAIN_CATEGORY_DETAIL。"""

    code = "JOB_STATE_INVALID_TRANSITION"

    def __init__(self, current: JobStatus, target: JobStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"illegal transition: {current.value} → {target.value}")


@dataclass(frozen=True)
class JobError:
    """结构化错误记录（工业契约：不能只抛字符串）。"""

    code: str  # DOMAIN_CATEGORY_DETAIL，如 JOB_PLAN_EMPTY
    message: str
    owner_module: str
    retryable: bool = False
    suggested_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "owner_module": self.owner_module,
            "retryable": self.retryable,
            "suggested_action": self.suggested_action,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobError:
        return cls(
            code=data["code"],
            message=data["message"],
            owner_module=data["owner_module"],
            retryable=bool(data.get("retryable", False)),
            suggested_action=data.get("suggested_action", ""),
        )


@dataclass(frozen=True)
class ModJob:
    """一次 Mod 生成任务的聚合根（不可变，迁移产生新实例）。"""

    job_id: str
    game_root: str
    intent: str
    status: JobStatus
    created_at: float
    updated_at: float
    artifacts_dir: str
    error: JobError | None = None
    # 阶段快照：graph_checksum / patch 摘要 / package 路径等（ORCH-JOB-02）
    checkpoint: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(cls, game_root: str, intent: str, artifacts_dir: str) -> ModJob:
        now = time.time()
        return cls(
            job_id=uuid.uuid4().hex[:12],
            game_root=game_root,
            intent=intent,
            status=JobStatus.CREATED,
            created_at=now,
            updated_at=now,
            artifacts_dir=artifacts_dir,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_progressing(self) -> bool:
        return self.status in _PROGRESSING

    def with_status(
        self,
        target: JobStatus,
        *,
        error: JobError | None = None,
        checkpoint_update: dict[str, Any] | None = None,
    ) -> ModJob:
        """校验迁移合法性后返回新实例；非法迁移抛 InvalidTransitionError。"""
        if target not in ALLOWED_TRANSITIONS[self.status]:
            raise InvalidTransitionError(self.status, target)
        new_checkpoint = dict(self.checkpoint)
        if checkpoint_update:
            new_checkpoint.update(checkpoint_update)
        return replace(
            self,
            status=target,
            updated_at=time.time(),
            error=error if target == JobStatus.FAILED else self.error,
            checkpoint=new_checkpoint,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "game_root": self.game_root,
            "intent": self.intent,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "artifacts_dir": self.artifacts_dir,
            "error": self.error.to_dict() if self.error else None,
            "checkpoint": self.checkpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModJob:
        return cls(
            job_id=data["job_id"],
            game_root=data["game_root"],
            intent=data["intent"],
            status=JobStatus(data["status"]),
            created_at=float(data["created_at"]),
            updated_at=float(data["updated_at"]),
            artifacts_dir=data["artifacts_dir"],
            error=JobError.from_dict(data["error"]) if data.get("error") else None,
            checkpoint=dict(data.get("checkpoint") or {}),
        )


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "InvalidTransitionError",
    "JobError",
    "JobStatus",
    "ModJob",
]
