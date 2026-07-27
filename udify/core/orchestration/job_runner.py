"""
JobRunner（ORCH-JOB-02/03，2026-08 批次 4A）。

把 Miu2dClosedLoop 的三个阶段（perceive/plan/preview）步进到 ModJob 状态机上，
产出可恢复的 durable 任务：

- ``advance_to_review``：created → perceiving → planning → awaiting_review。
- ``approve``：awaiting_review → applying → validating → packaging → completed。
- ``reject`` / ``rollback``：人工门的另外两个出口。
- ``resume`` / ``recover_incomplete``：崩溃后从状态快照继续（ORCH-JOB-03）。

关键安全语义：
- 全程只写 VFS 与 job 工件目录，**永不写 game_root**（红线 #5：产物是
  ModPackage，不是就地改档）。
- approve 时重新感知并比对 ``graph_checksum``——图版本漂移直接失败
  （工业契约：graph_version 不一致必须拒绝，不允许"尽量应用"）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from udify.core.miu2d_pipeline import Miu2dClosedLoop
from udify.core.mod_manager.mod_exporter import ModExporter, ModManifest
from udify.core.orchestration.job_store import JobStore
from udify.core.orchestration.mod_job import JobError, JobStatus, ModJob
from udify.core.validation.runtime_probe import HeadlessRuntimeProbe, probes_for_graph
from udify.core.validation.static_validator import StaticValidatorV3
from udify.models.cdl_patch import CDLPatch


class JobInputError(Exception):
    """任务输入非法（如 game_root 不存在）。"""

    def __init__(self, error: JobError) -> None:
        self.error = error
        super().__init__(error.message)


class JobRunner:
    """驱动 ModJob 状态机的本地执行器（单进程，同步步进）。"""

    def __init__(self, store: JobStore, artifacts_root: Path) -> None:
        self._store = store
        self._artifacts_root = artifacts_root

    # ----------------------------------------------------------------- create

    def create_job(self, game_root: str, intent: str) -> ModJob:
        root = Path(game_root)
        if not root.is_dir():
            raise JobInputError(
                JobError(
                    code="JOB_INPUT_INVALID_GAME_ROOT",
                    message=f"game_root 不是有效目录: {game_root}",
                    owner_module="orchestration.job_runner",
                    retryable=False,
                    suggested_action="确认路径存在且指向 miu2d 游戏目录",
                )
            )
        if not intent.strip():
            raise JobInputError(
                JobError(
                    code="JOB_INPUT_EMPTY_INTENT",
                    message="意图不能为空",
                    owner_module="orchestration.job_runner",
                    retryable=False,
                    suggested_action="用自然语言描述想要的修改",
                )
            )
        job = ModJob.new(game_root=str(root.resolve()), intent=intent, artifacts_dir="")
        artifacts_dir = self._artifacts_root / job.job_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        job = ModJob(
            job_id=job.job_id,
            game_root=job.game_root,
            intent=job.intent,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            artifacts_dir=str(artifacts_dir),
        )
        self._store.save(job)
        self._store.append_event(
            job.job_id,
            stage="created",
            event="job_created",
            payload={
                "game_root": job.game_root,
                "intent": job.intent,
            },
        )
        return job

    # ------------------------------------------------------------- to review

    def advance_to_review(self, job_id: str) -> ModJob:
        """created → … → awaiting_review（或 failed）。可重入：崩溃后重跑覆盖工件。"""
        job = self._require(job_id)
        loop = Miu2dClosedLoop(Path(job.game_root))
        artifacts = Path(job.artifacts_dir)

        # 阶段：perceiving
        if job.status == JobStatus.CREATED:
            job = self._store.transition(job, JobStatus.PERCEIVING, event="stage_started")
        elif job.status == JobStatus.PERCEIVING:
            self._store.append_event(job_id, stage="perceiving", event="stage_resumed")
        else:
            return self._resume_from(job)

        try:
            graph = loop.perceive()
        except Exception as e:  # 感知失败是数据问题，不是程序缺陷
            return self._fail(job, "JOB_PERCEIVE_FAILED", f"感知失败: {e}", retryable=True)
        graph_checksum = graph.checksum()
        _write_json(artifacts / "graph.json", graph.to_dict())

        # 阶段：planning
        job = self._store.transition(
            job,
            JobStatus.PLANNING,
            event="stage_started",
            payload={"nodes": len(graph.nodes), "graph_checksum": graph_checksum},
            checkpoint_update={"graph_checksum": graph_checksum},
        )
        actions, patch, plan_errors = loop.plan(graph, job.intent)
        if patch is None:
            return self._fail(
                job,
                "JOB_PLAN_EMPTY",
                "; ".join(plan_errors) or "无法生成计划",
                retryable=False,
                suggested_action="换一种表述，或确认游戏目录里有可解析的内容文件",
            )

        vfs, op_errors, fatal = loop.preview(patch)
        if fatal is not None:
            return self._fail(job, "JOB_PREVIEW_FAILED", fatal, retryable=True)

        # 审阅期静态验证（信息性；权威门在 validating 阶段）
        static_report = StaticValidatorV3().validate(patch, graph, vfs.get_all_diffs())

        _write_json(artifacts / "patch.json", patch.to_dict())
        _write_json(
            artifacts / "plan.json",
            {
                "intent": job.intent,
                "graph_checksum": graph_checksum,
                "actions": [
                    {
                        "schema": a.schema_name,
                        "target": a.target_node_id,
                        "params": a.params,
                        "reason": a.reason,
                    }
                    for a in actions
                ],
                "operations": [op.to_dict() for op in patch.operations],
                "diffs": vfs.get_all_diffs(),
                "op_errors": op_errors,
                "static_validation": static_report.to_dict(),
            },
        )

        # 阶段：awaiting_review（人工门，ORCH-JOB-03 pause）
        return self._store.transition(
            job,
            JobStatus.AWAITING_REVIEW,
            event="review_requested",
            payload={
                "operations": len(patch.operations),
                "files_affected": len(vfs.get_modified_files()),
                "static_errors": len(static_report.blocking_errors),
                "static_warnings": len(static_report.warnings),
            },
            checkpoint_update={"operations": len(patch.operations)},
        )

    # ---------------------------------------------------------------- gates

    def approve(self, job_id: str) -> ModJob:
        """人工批准：awaiting_review → applying → validating → packaging → completed。"""
        job = self._require(job_id)
        artifacts = Path(job.artifacts_dir)
        loop = Miu2dClosedLoop(Path(job.game_root))

        if job.status == JobStatus.AWAITING_REVIEW:
            job = self._store.transition(job, JobStatus.APPLYING, event="approved")
        elif job.status in {JobStatus.APPLYING, JobStatus.VALIDATING, JobStatus.PACKAGING}:
            self._store.append_event(job_id, stage=job.status.value, event="stage_resumed")
        else:
            raise JobInputError(_state_error(job, "approve 仅在 awaiting_review 状态可用"))

        # 重新感知 + 图版本守卫（工业契约 #8）
        try:
            graph = loop.perceive()
        except Exception as e:
            return self._fail(job, "JOB_PERCEIVE_FAILED", f"感知失败: {e}", retryable=True)
        expected = job.checkpoint.get("graph_checksum")
        actual = graph.checksum()
        if expected and actual != expected:
            return self._fail(
                job,
                "JOB_GRAPH_VERSION_MISMATCH",
                f"游戏文件在审阅后发生变化（checksum {expected[:12]}… → {actual[:12]}…），拒绝应用",
                retryable=False,
                suggested_action="重新创建任务，基于当前游戏状态重新规划",
            )

        patch = CDLPatch.from_dict(json.loads((artifacts / "patch.json").read_text()))
        vfs, op_errors, fatal = loop.preview(patch)
        if fatal is not None or op_errors:
            detail = fatal or "; ".join(op_errors)
            return self._fail(job, "JOB_APPLY_FAILED", detail, retryable=True)

        modified = vfs.get_modified_files()
        files_dir = artifacts / "files"
        for rel in modified:
            content = vfs.read_file(rel)
            if content is None:
                continue
            out = files_dir / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content)

        # 阶段：validating（权威门）
        if job.status == JobStatus.APPLYING:
            job = self._store.transition(
                job,
                JobStatus.VALIDATING,
                event="stage_started",
                payload={"files_modified": len(modified)},
            )
        vfs_diffs = vfs.get_all_diffs()
        static_report = StaticValidatorV3().validate(patch, graph, vfs_diffs)
        probe_report = HeadlessRuntimeProbe().run(graph, probes_for_graph(graph), vfs_diffs)
        _write_json(
            artifacts / "report.json",
            {
                "static_validation": static_report.to_dict(),
                "probe": probe_report.to_dict(),
                "graph_checksum_before": expected,
                "graph_checksum_applied_on": actual,
            },
        )
        if static_report.blocking_errors:
            return self._fail(
                job,
                "JOB_VALIDATION_BLOCKED",
                f"静态验证阻塞错误 {len(static_report.blocking_errors)} 条，详见 report.json",
                retryable=False,
                suggested_action="查看 report.json 的 blocking_errors，调整意图后重试",
            )

        # 阶段：packaging
        if job.status == JobStatus.VALIDATING:
            job = self._store.transition(job, JobStatus.PACKAGING, event="stage_started")
        manifest = ModManifest(
            mod_id=f"udify_{job.job_id}",
            name=(job.intent[:40] or "udify mod"),
            version="1.0.0",
            author="udify",
            description=job.intent,
            game_id="miu2d",
            operations_count=len(patch.operations),
            files_modified=modified,
        )
        mod_files = {rel: c for rel in modified if (c := vfs.read_file(rel)) is not None}
        package_path = ModExporter(artifacts).export_zip(patch, manifest, mod_files)

        return self._store.transition(
            job,
            JobStatus.COMPLETED,
            event="job_completed",
            payload={
                "package": package_path.name,
                "probe_passed": probe_report.to_dict().get("passed"),
            },
            checkpoint_update={"package": str(package_path)},
        )

    def reject(self, job_id: str, reason: str = "") -> ModJob:
        job = self._require(job_id)
        if job.status != JobStatus.AWAITING_REVIEW:
            raise JobInputError(_state_error(job, "reject 仅在 awaiting_review 状态可用"))
        return self._store.transition(
            job, JobStatus.REJECTED, event="rejected", payload={"reason": reason}
        )

    def rollback(self, job_id: str) -> ModJob:
        """回滚：completed/failed → compensating → rolled_back。

        产物从未写入 game_root，因此回滚 = 作废 ModPackage + 验证原始图
        checksum 未被本任务改变（成功判据 #6 的产品化表达）。
        """
        job = self._require(job_id)
        if job.status not in {JobStatus.COMPLETED, JobStatus.FAILED}:
            raise JobInputError(_state_error(job, "rollback 仅在 completed/failed 状态可用"))
        job = self._store.transition(job, JobStatus.COMPENSATING, event="rollback_started")

        baseline = job.checkpoint.get("graph_checksum")
        try:
            current = Miu2dClosedLoop(Path(job.game_root)).perceive().checksum()
        except Exception as e:
            return self._fail(
                job, "JOB_ROLLBACK_VERIFY_FAILED", f"回滚校验失败: {e}", retryable=True
            )
        checksum_intact = baseline is None or current == baseline

        package = job.checkpoint.get("package")
        revoked = None
        if package and Path(package).exists():
            revoked = str(Path(package).with_suffix(".zip.rolled_back"))
            Path(package).rename(revoked)

        return self._store.transition(
            job,
            JobStatus.ROLLED_BACK,
            event="rolled_back",
            payload={"checksum_intact": checksum_intact, "package_revoked": revoked},
            checkpoint_update={"package_revoked": revoked},
        )

    # --------------------------------------------------------------- recover

    def resume(self, job_id: str) -> ModJob:
        """崩溃恢复入口：按当前状态把 job 推进到下一个稳定点。"""
        return self._resume_from(self._require(job_id))

    def recover_incomplete(self) -> list[ModJob]:
        """启动时扫描所有中断的进行态任务并恢复（awaiting_review 保持等待）。"""
        stuck = self._store.list_by_status(
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
        return [self._resume_from(j) for j in stuck]

    def _resume_from(self, job: ModJob) -> ModJob:
        if job.status in {JobStatus.CREATED, JobStatus.PERCEIVING, JobStatus.PLANNING}:
            # 规划是确定性的，从头重跑并覆盖工件
            if job.status != JobStatus.CREATED:
                self._store.append_event(job.job_id, stage=job.status.value, event="recovered")
            return (
                self.advance_to_review(job.job_id)
                if job.status == JobStatus.CREATED
                else (self._replan(job))
            )
        if job.status in {JobStatus.APPLYING, JobStatus.VALIDATING, JobStatus.PACKAGING}:
            self._store.append_event(job.job_id, stage=job.status.value, event="recovered")
            return self.approve(job.job_id)
        return job  # awaiting_review / 终态：无事可做

    def _replan(self, job: ModJob) -> ModJob:
        """从 perceiving/planning 中断处恢复：直接重走 advance 流程主体。"""
        # 状态已在进行态，advance_to_review 的重入分支会处理
        loop = Miu2dClosedLoop(Path(job.game_root))
        artifacts = Path(job.artifacts_dir)
        try:
            graph = loop.perceive()
        except Exception as e:
            return self._fail(job, "JOB_PERCEIVE_FAILED", f"感知失败: {e}", retryable=True)
        graph_checksum = graph.checksum()
        _write_json(artifacts / "graph.json", graph.to_dict())
        if job.status == JobStatus.PERCEIVING:
            job = self._store.transition(
                job,
                JobStatus.PLANNING,
                event="stage_started",
                payload={"nodes": len(graph.nodes), "resumed": True},
                checkpoint_update={"graph_checksum": graph_checksum},
            )
        actions, patch, plan_errors = loop.plan(graph, job.intent)
        if patch is None:
            return self._fail(
                job, "JOB_PLAN_EMPTY", "; ".join(plan_errors) or "无法生成计划", retryable=False
            )
        vfs, op_errors, fatal = loop.preview(patch)
        if fatal is not None:
            return self._fail(job, "JOB_PREVIEW_FAILED", fatal, retryable=True)
        static_report = StaticValidatorV3().validate(patch, graph, vfs.get_all_diffs())
        _write_json(artifacts / "patch.json", patch.to_dict())
        _write_json(
            artifacts / "plan.json",
            {
                "intent": job.intent,
                "graph_checksum": graph_checksum,
                "actions": [
                    {
                        "schema": a.schema_name,
                        "target": a.target_node_id,
                        "params": a.params,
                        "reason": a.reason,
                    }
                    for a in actions
                ],
                "operations": [op.to_dict() for op in patch.operations],
                "diffs": vfs.get_all_diffs(),
                "op_errors": op_errors,
                "static_validation": static_report.to_dict(),
            },
        )
        return self._store.transition(
            job,
            JobStatus.AWAITING_REVIEW,
            event="review_requested",
            payload={"operations": len(patch.operations), "resumed": True},
            checkpoint_update={"operations": len(patch.operations)},
        )

    # ----------------------------------------------------------------- utils

    def _require(self, job_id: str) -> ModJob:
        job = self._store.get(job_id)
        if job is None:
            raise JobInputError(
                JobError(
                    code="JOB_QUERY_NOT_FOUND",
                    message=f"任务不存在: {job_id}",
                    owner_module="orchestration.job_runner",
                    retryable=False,
                    suggested_action="用 GET /jobs 查看任务列表",
                )
            )
        return job

    def _fail(
        self,
        job: ModJob,
        code: str,
        message: str,
        *,
        retryable: bool,
        suggested_action: str = "",
    ) -> ModJob:
        return self._store.transition(
            job,
            JobStatus.FAILED,
            event="job_failed",
            error=JobError(
                code=code,
                message=message,
                owner_module="orchestration.job_runner",
                retryable=retryable,
                suggested_action=suggested_action,
            ),
        )


def _state_error(job: ModJob, message: str) -> JobError:
    return JobError(
        code="JOB_STATE_INVALID_TRANSITION",
        message=f"{message}（当前: {job.status.value}）",
        owner_module="orchestration.job_runner",
        retryable=False,
        suggested_action="查询任务当前状态后按状态机操作",
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))


__all__ = ["JobInputError", "JobRunner"]
