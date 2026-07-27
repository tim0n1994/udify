"""
薄 API（API-01..08 + SRV-01，2026-08 批次 4B）。

ADR-v3-007：FastAPI + Pydantic v2，默认 127.0.0.1 单用户免认证；
所有 JSON 端点走统一信封；错误码 DOMAIN_CATEGORY_DETAIL。
ADR-v3-008：进度靠轮询 ``GET /jobs/{id}``（事件流支持 after_seq 增量拉取）。

安全模型：本机单用户。重活（规划/应用）在进程内线程池执行，
每个 job 有 in-flight 守卫防止重复驱动。
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse

from udify.api.schemas import CreateJobRequest, Envelope, RejectRequest
from udify.core.orchestration import (
    InvalidTransitionError,
    JobError,
    JobInputError,
    JobRunner,
    JobStatus,
    JobStore,
)

API_VERSION = "v0"
UDIFY_VERSION = "0.2.0-dev"

logger = logging.getLogger("udify.api")


class ApiState:
    """应用级状态：存储、执行器与 in-flight 守卫。"""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.store = JobStore(state_dir / "jobs.db")
        self.runner = JobRunner(self.store, state_dir / "jobs")
        # ponytail: 2 个工作线程对单用户本地场景绰绰有余；多用户是非目标（红线 #11）
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="udify-job")
        self.inflight: set[str] = set()
        self.lock = threading.Lock()

    def submit_exclusive(self, job_id: str, fn: Callable[[], Any]) -> bool:
        """为 job 提交独占后台任务；已有在跑的任务则返回 False。"""
        with self.lock:
            if job_id in self.inflight:
                return False
            self.inflight.add(job_id)

        def _run() -> None:
            try:
                fn()
            except Exception:
                logger.exception("background task failed for job %s", job_id)
            finally:
                with self.lock:
                    self.inflight.discard(job_id)

        self.executor.submit(_run)
        return True


def _ok(data: Any, status_code: int = 200, meta: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": True, "data": data, "error": None, "meta": meta},
    )


def _err(error: JobError, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": error.to_dict(), "meta": None},
    )


def _status_for(code: str) -> int:
    if "_NOT_FOUND" in code or "_NOT_READY" in code or "_NOT_AVAILABLE" in code:
        return 404
    if code.startswith("JOB_INPUT_"):
        return 400
    if "_STATE_" in code or "_BUSY" in code:
        return 409
    return 500


def create_app(state_dir: Path | None = None) -> FastAPI:
    """App 工厂。state_dir 默认 ``./.udify``（与 CLI 共享状态目录）。"""
    resolved_state = (state_dir or Path(".udify")).resolve()
    state = ApiState(resolved_state)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # 崩溃恢复（ORCH-JOB-03）：把中断的进行态任务推回稳定点
        stuck = state.store.list_by_status(
            frozenset(
                {
                    JobStatus.CREATED,
                    JobStatus.PERCEIVING,
                    JobStatus.PLANNING,
                    JobStatus.APPLYING,
                    JobStatus.VALIDATING,
                    JobStatus.PACKAGING,
                }
            )
        )
        for job in stuck:
            state.submit_exclusive(job.job_id, partial(state.runner.resume, job.job_id))
        if stuck:
            logger.info("recovering %d incomplete jobs", len(stuck))
        yield
        state.executor.shutdown(wait=False, cancel_futures=True)
        state.store.close()

    app = FastAPI(
        title="Udify API",
        version=UDIFY_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.udify = state  # 测试可直达

    @app.exception_handler(JobInputError)
    async def _job_input_error(_: Request, exc: JobInputError) -> JSONResponse:
        return _err(exc.error, _status_for(exc.error.code))

    @app.exception_handler(InvalidTransitionError)
    async def _transition_error(_: Request, exc: InvalidTransitionError) -> JSONResponse:
        return _err(
            JobError(
                code=exc.code,
                message=str(exc),
                owner_module="orchestration.mod_job",
                retryable=False,
                suggested_action="查询任务当前状态后按状态机操作",
            ),
            409,
        )

    prefix = f"/api/{API_VERSION}"

    @app.get(f"{prefix}/healthz", response_model=Envelope)
    async def healthz() -> JSONResponse:
        return _ok(
            {
                "version": UDIFY_VERSION,
                "api_version": API_VERSION,
                "state_dir": str(state.state_dir),
                "engines": {"miu2d": True},
            }
        )

    @app.post(f"{prefix}/jobs", response_model=Envelope, status_code=202)
    async def create_job(body: CreateJobRequest) -> JSONResponse:
        job = state.runner.create_job(body.game_root, body.intent)
        state.submit_exclusive(job.job_id, lambda: state.runner.advance_to_review(job.job_id))
        return _ok(job.to_dict(), status_code=202)

    @app.get(f"{prefix}/jobs", response_model=Envelope)
    async def list_jobs(limit: int = 50, offset: int = 0) -> JSONResponse:
        jobs = state.store.list_jobs(limit=min(limit, 200), offset=offset)
        return _ok([j.to_dict() for j in jobs], meta={"limit": limit, "offset": offset})

    @app.get(f"{prefix}/jobs/{{job_id}}", response_model=Envelope)
    async def get_job(job_id: str, after_seq: int = 0) -> JSONResponse:
        job = _require_job(state, job_id)
        events = state.store.events(job_id, after_seq=after_seq)
        return _ok(
            {
                "job": job.to_dict(),
                "events": [e.to_dict() for e in events],
                "audit_chain_valid": state.store.verify_chain(job_id),
            }
        )

    @app.get(f"{prefix}/jobs/{{job_id}}/plan", response_model=Envelope)
    async def get_plan(job_id: str) -> JSONResponse:
        job = _require_job(state, job_id)
        return _ok(_read_artifact(job.artifacts_dir, "plan.json"))

    @app.post(f"{prefix}/jobs/{{job_id}}/approve", response_model=Envelope, status_code=202)
    async def approve(job_id: str) -> JSONResponse:
        job = _require_job(state, job_id)
        if job.status != JobStatus.AWAITING_REVIEW:
            raise JobInputError(
                JobError(
                    code="JOB_STATE_INVALID_TRANSITION",
                    message=f"approve 仅在 awaiting_review 状态可用（当前: {job.status.value}）",
                    owner_module="api",
                    retryable=False,
                    suggested_action="轮询 GET /jobs/{id} 查看当前状态",
                )
            )
        if not state.submit_exclusive(job_id, lambda: state.runner.approve(job_id)):
            raise JobInputError(_busy(job_id))
        return _ok(job.to_dict(), status_code=202)

    @app.post(f"{prefix}/jobs/{{job_id}}/reject", response_model=Envelope)
    async def reject(job_id: str, body: RejectRequest | None = None) -> JSONResponse:
        reason = body.reason if body else ""
        job = state.runner.reject(job_id, reason=reason)
        return _ok(job.to_dict())

    @app.get(f"{prefix}/jobs/{{job_id}}/report", response_model=Envelope)
    async def get_report(job_id: str) -> JSONResponse:
        job = _require_job(state, job_id)
        return _ok(_read_artifact(job.artifacts_dir, "report.json"))

    @app.get(f"{prefix}/jobs/{{job_id}}/package")
    async def get_package(job_id: str) -> FileResponse:
        job = _require_job(state, job_id)
        package = job.checkpoint.get("package")
        if not package or not Path(package).exists():
            raise JobInputError(
                JobError(
                    code="JOB_PACKAGE_NOT_AVAILABLE",
                    message="ModPackage 不存在（任务未完成或已回滚作废）",
                    owner_module="api",
                    retryable=False,
                    suggested_action="确认任务处于 completed 状态",
                )
            )
        return FileResponse(package, media_type="application/zip", filename=Path(package).name)

    @app.post(f"{prefix}/jobs/{{job_id}}/rollback", response_model=Envelope)
    async def rollback(job_id: str) -> JSONResponse:
        # ponytail: 同步执行（感知+checksum，小游戏毫秒级）；大游戏慢了再改后台
        job = state.runner.rollback(job_id)
        return _ok(job.to_dict())

    @app.get(f"{prefix}/mods", response_model=Envelope)
    async def list_mods(game_root: str) -> JSONResponse:
        """MOD-STACK-01..03 最小接线：某游戏已产出的 Mod 列表 + 同 target 冲突。"""
        resolved = str(Path(game_root).resolve())
        completed = [
            j
            for j in state.store.list_jobs(limit=200)
            if j.status == JobStatus.COMPLETED and j.game_root == resolved
        ]
        mods: list[dict[str, Any]] = []
        op_targets: dict[str, set[str]] = {}
        for j in completed:
            patch_path = Path(j.artifacts_dir) / "patch.json"
            targets: set[str] = set()
            op_count = 0
            if patch_path.exists():
                ops = json.loads(patch_path.read_text()).get("operations", [])
                op_count = len(ops)
                targets = {op["target_id"] for op in ops}
            op_targets[j.job_id] = targets
            mods.append(
                {
                    "job_id": j.job_id,
                    "intent": j.intent,
                    "package": j.checkpoint.get("package"),
                    "operations": op_count,
                    "created_at": j.created_at,
                }
            )
        conflicts = [
            {
                "job_a": a,
                "job_b": b,
                "shared_targets": sorted(op_targets[a] & op_targets[b]),
            }
            for i, a in enumerate(op_targets)
            for b in list(op_targets)[i + 1 :]
            if op_targets[a] & op_targets[b]
        ]
        return _ok({"mods": mods, "conflicts": conflicts})

    return app


def _require_job(state: ApiState, job_id: str) -> Any:
    job = state.store.get(job_id)
    if job is None:
        raise JobInputError(
            JobError(
                code="JOB_QUERY_NOT_FOUND",
                message=f"任务不存在: {job_id}",
                owner_module="api",
                retryable=False,
                suggested_action="用 GET /jobs 查看任务列表",
            )
        )
    return job


def _read_artifact(artifacts_dir: str, name: str) -> dict[str, Any]:
    path = Path(artifacts_dir) / name
    if not path.exists():
        raise JobInputError(
            JobError(
                code="JOB_ARTIFACT_NOT_READY",
                message=f"工件尚未生成: {name}",
                owner_module="api",
                retryable=True,
                suggested_action="任务仍在推进中，稍后重试或轮询任务状态",
            )
        )
    return json.loads(path.read_text())  # type: ignore[no-any-return]


def _busy(job_id: str) -> JobError:
    return JobError(
        code="JOB_STATE_BUSY",
        message=f"任务 {job_id} 已有后台操作在执行",
        owner_module="api",
        retryable=True,
        suggested_action="等待当前操作完成后重试",
    )


__all__ = ["API_VERSION", "UDIFY_VERSION", "create_app"]
