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

import hashlib
import json
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from udify.core.miu2d_pipeline import IntentClarification, Miu2dClosedLoop
from udify.core.mod_manager.mod_exporter import ModExporter, ModManifest
from udify.core.orchestration.gate_orchestrator import (
    DeliveryTier,
    GateOrchestrator,
)
from udify.core.orchestration.job_store import JobStore
from udify.core.orchestration.mod_job import JobError, JobStatus, ModJob
from udify.core.validation.runtime_probe import ProbeReport
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
        if _detect_engine_id(root) != "miu2d":
            raise JobInputError(
                JobError(
                    code="JOB_INPUT_UNSUPPORTED_ENGINE",
                    message="当前工作台仅支持 miu2d 文件包生成",
                    owner_module="orchestration.job_runner",
                    suggested_action="选择 miu2d 内容目录",
                )
            )
        self._validate_storage_root(root)
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
        if job.status == JobStatus.CREATED:
            job = self._store.transition(job, JobStatus.PERCEIVING, event="stage_started")
        if job.status not in {JobStatus.PERCEIVING, JobStatus.PLANNING}:
            return self._resume_from(job)
        try:
            self._validate_storage_root(Path(job.game_root))
            return self._replan(job)
        except Exception as exc:
            return self.record_failure(job_id, exc)

    # ---------------------------------------------------------------- gates

    def approve(self, job_id: str) -> ModJob:
        """人工批准：awaiting_review → applying → validating → packaging → completed。"""
        try:
            return self._approve(job_id)
        except JobInputError:
            raise
        except Exception as exc:
            return self.record_failure(job_id, exc)

    def _approve(self, job_id: str) -> ModJob:
        job = self._require(job_id)
        artifacts = self._job_artifacts(job)
        loop = Miu2dClosedLoop(Path(job.game_root))
        self._validate_storage_root(Path(job.game_root))

        if job.status not in {
            JobStatus.AWAITING_REVIEW,
            JobStatus.APPLYING,
            JobStatus.VALIDATING,
            JobStatus.PACKAGING,
        }:
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

        approval = job.checkpoint.get("approval")
        if (
            not self._store.verify_chain(job_id)
            or not approval
            or (approval != self._approval_snapshot(job))
        ):
            return self._fail(
                job,
                "JOB_APPROVAL_INTEGRITY_FAILED",
                "审阅工件、源文件或审计链已改变，拒绝批准",
                retryable=False,
            )
        if job.status == JobStatus.AWAITING_REVIEW:
            job = self._store.transition(
                job, JobStatus.APPLYING, event="approved", payload={"approval": approval}
            )
        patch = CDLPatch.from_dict(json.loads((artifacts / "patch.json").read_text()))
        plan = json.loads((artifacts / "plan.json").read_text())
        vfs, op_errors, fatal = loop.preview(patch)
        if fatal is not None or op_errors:
            detail = fatal or "; ".join(op_errors)
            return self._fail(job, "JOB_APPLY_FAILED", detail, retryable=True)

        reviewed_files = {diff["path"]: diff["current"] for diff in plan["diffs"]}
        actual_files = {diff["path"]: diff["current"] for diff in vfs.get_all_diffs()}
        if reviewed_files != actual_files:
            return self._fail(
                job,
                "JOB_ARTIFACT_VALIDATION_FAILED",
                "执行输出的文件清单或字节与审阅计划不一致",
                retryable=False,
            )

        modified = sorted(vfs.get_modified_files())
        files_dir = artifacts / "files"
        for rel in modified:
            content = vfs.read_file(rel)
            if content is None:
                continue
            out = _contained_path(artifacts, f"files/{rel}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(content.encode("utf-8"))

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

        artifact_validation = _validate_staged_artifacts(patch, files_dir, graph, reviewed_files)
        probe_report = ProbeReport(passed=False, engine_coverage="UNVERIFIABLE")

        # M3-PR1：五道闸门编排。此前 GateOrchestrator 零调用者，JobRunner 是线性
        # glue，没有统一降级策略。final_tier 取所有阻断闸门的最低值。
        verdict = GateOrchestrator().run_gates(
            job.job_id,
            _JobGateContext(
                graph=graph,
                intent=job.intent,
                patch=patch,
                manifests=(),
                resolved_targets=[op.target_id for op in patch.operations],
                ambiguous=False,
                sandboxed=False,
                validation_passed=None,
                validation_skipped=True,
                dependency_conflicts=[],
            ),
        )

        report = {
            "delivery": {
                "kind": "package",
                "installed": False,
                "tier": "STATIC_ONLY",
                "reason": "仅验证补丁文件的静态结构与精确目标值；未安装、未运行游戏",
            },
            "artifact_validation": artifact_validation,
            "approval": approval,
            "artifacts": [_file_hash(files_dir, rel, prefix="files/") for rel in modified],
            "static_validation": static_report.to_dict(),
            "probe": {
                **probe_report.to_dict(),
                "skipped": True,
                "reason": "package-only delivery does not launch or observe the game",
            },
            "engine_coverage": probe_report.engine_coverage,
            "gate_verdict": {
                "final_tier": verdict.final_tier.value,
                "final_tier_reason": verdict.final_tier_reason,
                "gates": [
                    {
                        "name": g.name.value,
                        "lifecycle": g.lifecycle.value,
                        "verdict": g.verdict.value,
                        "evidence": g.evidence,
                        "delivery_tier": g.delivery_tier.value,
                    }
                    for g in verdict.gates
                ],
            },
            "graph_checksum_before": expected,
            "graph_checksum_applied_on": actual,
        }
        _write_json(artifacts / "report.json", report)
        if not artifact_validation["passed"]:
            return self._fail(
                job,
                "JOB_ARTIFACT_VALIDATION_FAILED",
                "补丁工件未实现已批准的精确操作，详见 report.json",
                retryable=False,
            )
        if static_report.blocking_errors:
            return self._fail(
                job,
                "JOB_VALIDATION_BLOCKED",
                f"静态验证阻塞错误 {len(static_report.blocking_errors)} 条，详见 report.json",
                retryable=False,
                suggested_action="查看 report.json 的 blocking_errors，调整意图后重试",
            )
        # 降级铁律：闸门判定 NONE（被阻断）时不得继续打包交付。
        if verdict.final_tier is DeliveryTier.NONE:
            return self._fail(
                job,
                "JOB_GATE_BLOCKED",
                f"闸门阻断：{verdict.final_tier_reason}",
                retryable=False,
                suggested_action="查看 report.json 的 gate_verdict，按 evidence 调整后重试",
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
        mod_files = {
            rel: _contained_path(files_dir, rel).read_bytes().decode("utf-8") for rel in modified
        }
        package_path = ModExporter(artifacts).export_zip(patch, manifest, mod_files)
        with zipfile.ZipFile(package_path) as package:
            if set(package.namelist()) != {"manifest.json", "patch.json", "README.md"} | {
                f"files/{rel}" for rel in mod_files
            }:
                raise ValueError("package inventory differs from reviewed files")
            for rel, content in mod_files.items():
                if package.read(f"files/{rel}") != content.encode("utf-8"):
                    raise ValueError(f"package content mismatch: {rel}")
            if json.loads(package.read("patch.json")) != patch.to_dict():
                raise ValueError("package patch mismatch")
        if report["artifacts"] != [_file_hash(files_dir, rel, prefix="files/") for rel in modified]:
            raise ValueError("staged artifacts changed during packaging")
        if approval != self._approval_snapshot(job):
            return self._fail(
                job,
                "JOB_APPROVAL_INTEGRITY_FAILED",
                "生成期间源文件或审阅工件发生变化",
                retryable=False,
            )
        package_hash = _file_hash(artifacts, package_path.name)
        report["artifacts"].append(package_hash)
        _write_json(artifacts / "report.json", report)

        return self._store.transition(
            job,
            JobStatus.COMPLETED,
            event="job_completed",
            payload={
                "package": package_path.name,
                "probe_passed": probe_report.to_dict().get("passed"),
            },
            checkpoint_update={
                "package": str(package_path),
                "package_sha256": package_hash["sha256"],
            },
        )

    def reject(self, job_id: str, reason: str = "") -> ModJob:
        job = self._require(job_id)
        if job.status not in {JobStatus.AWAITING_REVIEW, JobStatus.AWAITING_CLARIFICATION}:
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
        if job.status == JobStatus.ROLLED_BACK:
            return job
        if job.status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.COMPENSATING}:
            raise JobInputError(_state_error(job, "rollback 仅在 completed/failed 状态可用"))
        if job.status != JobStatus.COMPENSATING:
            job = self._store.transition(job, JobStatus.COMPENSATING, event="rollback_started")
        try:
            return self._compensate(job)
        except Exception as exc:
            return self.record_failure(job_id, exc)

    def _compensate(self, job: ModJob) -> ModJob:
        package = job.checkpoint.get("package")
        revoked = None
        if package:
            package_path = _contained_path(self._job_artifacts(job), Path(package).name)
            revoked_path = package_path.with_suffix(".zip.rolled_back")
            if package_path.exists():
                if revoked_path.exists():
                    raise OSError("revocation destination already exists")
                package_path.rename(revoked_path)
            if revoked_path.exists():
                revoked = str(revoked_path)
        checksum_intact: bool | None = None
        source_integrity_reason = "未记录源文件基线；撤销操作仅作废文件包"
        baseline = job.checkpoint.get("graph_checksum")
        try:
            root = Path(job.game_root)
            if not root.is_dir():
                source_integrity_reason = "源目录不可用；文件包已作废，未执行游戏恢复"
            elif baseline:
                current = Miu2dClosedLoop(root).perceive().checksum()
                approval = job.checkpoint.get("approval")
                checksum_intact = current == baseline and (
                    not approval or approval["source_files"] == _source_hashes(root)
                )
                source_integrity_reason = (
                    "源文件与任务基线一致"
                    if checksum_intact
                    else "源文件已在任务外改变；文件包已作废，未执行游戏恢复"
                )
        except Exception as exc:
            source_integrity_reason = f"源文件无法核验：{exc}；文件包已作废"
        rollback = {
            "checksum_intact": checksum_intact,
            "source_integrity_reason": source_integrity_reason,
            "package_revoked": revoked,
        }

        return self._store.transition(
            job,
            JobStatus.ROLLED_BACK,
            event="rolled_back",
            payload=rollback,
            checkpoint_update={"package_revoked": revoked, "rollback": rollback},
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
                    JobStatus.COMPENSATING,
                }
            )
        )
        return [self.resume(j.job_id) for j in stuck]

    def _resume_from(self, job: ModJob) -> ModJob:
        if job.status in {JobStatus.CREATED, JobStatus.PERCEIVING, JobStatus.PLANNING}:
            # 规划是确定性的，从头重跑并覆盖工件
            if job.status != JobStatus.CREATED:
                self._store.append_event(job.job_id, stage=job.status.value, event="recovered")
            return self.advance_to_review(job.job_id)
        if job.status in {JobStatus.APPLYING, JobStatus.VALIDATING, JobStatus.PACKAGING}:
            self._store.append_event(job.job_id, stage=job.status.value, event="recovered")
            return self.approve(job.job_id)
        if job.status == JobStatus.COMPENSATING:
            return self.rollback(job.job_id)
        return job  # awaiting_review / 终态：无事可做

    def _replan(self, job: ModJob) -> ModJob:
        """从 perceiving/planning 中断处恢复：直接重走 advance 流程主体。"""
        # 状态已在进行态，advance_to_review 的重入分支会处理
        loop = Miu2dClosedLoop(Path(job.game_root))
        artifacts = self._job_artifacts(job)
        source_hashes = _source_hashes(Path(job.game_root))
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
        else:
            job = replace(job, checkpoint={**job.checkpoint, "graph_checksum": graph_checksum})
            self._store.save(job)
        try:
            target_ids = job.checkpoint.get("clarified_target_ids")
            if target_ids is None:
                actions, patch, plan_errors = loop.plan(graph, job.intent)
            else:
                actions, patch, plan_errors = loop.plan(graph, job.intent, target_ids=target_ids)
        except IntentClarification as exc:
            clarification = {
                "question": exc.question,
                "candidates": exc.candidates,
                "reason": exc.reason,
                "graph_checksum": graph_checksum,
            }
            return self._store.transition(
                job,
                JobStatus.AWAITING_CLARIFICATION,
                event="clarification_requested",
                payload=clarification,
                checkpoint_update={
                    "clarification": clarification,
                    "clarification_sources": source_hashes,
                },
            )
        if patch is None:
            return self._fail(
                job, "JOB_PLAN_EMPTY", "; ".join(plan_errors) or "无法生成计划", retryable=False
            )
        vfs, op_errors, fatal = loop.preview(patch)
        if fatal is not None or op_errors:
            return self._fail(
                job, "JOB_PREVIEW_FAILED", fatal or "; ".join(op_errors), retryable=True
            )
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
        approval = self._approval_snapshot(job)
        if approval["source_files"] != source_hashes:
            return self._fail(
                job,
                "JOB_GRAPH_VERSION_MISMATCH",
                "规划过程中源文件变化，请重新创建任务",
                retryable=False,
            )
        return self._store.transition(
            job,
            JobStatus.AWAITING_REVIEW,
            event="review_requested",
            payload={"operations": len(patch.operations), "approval": approval},
            checkpoint_update={
                "operations": len(patch.operations),
                "clarification": None,
                "approval": approval,
            },
        )

    # ----------------------------------------------------------------- utils

    def _job_artifacts(self, job: ModJob) -> Path:
        artifacts = Path(job.artifacts_dir)
        if not artifacts.resolve().is_relative_to(self._artifacts_root.resolve()):
            raise ValueError("job artifacts escape configured storage root")
        return artifacts

    def _validate_storage_root(self, root: Path) -> None:
        source = root.resolve()
        output = self._artifacts_root.resolve()
        if (
            output.is_relative_to(source)
            or source.is_relative_to(output)
            or self._store.db_path.resolve().is_relative_to(source)
        ):
            raise JobInputError(
                JobError(
                    "JOB_INPUT_OUTPUT_OVERLAP",
                    "游戏目录不能与任务工件目录或状态数据库重叠",
                    "orchestration.job_runner",
                    suggested_action="将 Udify 状态目录放在游戏目录外",
                )
            )

    def validate_clarification(self, job_id: str, target_ids: list[str]) -> None:
        """Validate a selection without advancing the durable clarification state."""
        job = self._require(job_id)
        if job.status != JobStatus.AWAITING_CLARIFICATION:
            raise JobInputError(_state_error(job, "任务当前不等待目标澄清"))
        clarification = job.checkpoint.get("clarification") or {}
        candidates = {item["node_id"] for item in clarification.get("candidates", [])}
        if (
            not target_ids
            or len(set(target_ids)) != len(target_ids)
            or not set(target_ids) <= candidates
        ):
            raise JobInputError(
                JobError(
                    "JOB_CLARIFICATION_INVALID_TARGET",
                    "选择必须来自当前候选目标",
                    "orchestration.job_runner",
                )
            )
        current = Miu2dClosedLoop(Path(job.game_root)).perceive().checksum()
        if current != clarification.get("graph_checksum") or (
            _source_hashes(Path(job.game_root)) != job.checkpoint.get("clarification_sources")
        ):
            raise JobInputError(
                JobError(
                    "JOB_GRAPH_VERSION_MISMATCH",
                    "澄清期间源文件已变化，请新建任务",
                    "orchestration.job_runner",
                )
            )

    def clarify(self, job_id: str, target_ids: list[str]) -> ModJob:
        """Persist valid target choices and continue planning to human review."""
        self.validate_clarification(job_id, target_ids)
        job = self._store.transition(
            self._require(job_id),
            JobStatus.PLANNING,
            event="clarification_answered",
            payload={"target_ids": target_ids},
            checkpoint_update={"clarified_target_ids": list(target_ids)},
        )
        return self.advance_to_review(job.job_id)

    def record_failure(self, job_id: str, exc: Exception) -> ModJob:
        """Persist unexpected worker failures without overwriting stable terminal results."""
        job = self._require(job_id)
        if job.status in {
            JobStatus.FAILED,
            JobStatus.COMPLETED,
            JobStatus.REJECTED,
            JobStatus.ROLLED_BACK,
        }:
            return job
        return self._fail(
            job,
            "JOB_ARTIFACT_IO_FAILED" if isinstance(exc, OSError) else "JOB_EXECUTION_FAILED",
            str(exc),
            retryable=True,
        )

    def _approval_snapshot(self, job: ModJob) -> dict[str, Any]:
        artifacts = self._job_artifacts(job)
        return {
            "plan_sha256": _file_hash(artifacts, "plan.json")["sha256"],
            "patch_sha256": _file_hash(artifacts, "patch.json")["sha256"],
            "source_files": _source_hashes(Path(job.game_root)),
        }

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


@dataclass
class _JobGateContext:
    """GateOrchestrator 的 GateContext 实现（M3-PR1）。

    闸门用 ``getattr`` 读取可选字段，因此这里必须把每个闸门需要的事实都显式提供，
    缺失即被当作"未提供"而降级——不要依赖默认值蒙混过关。
    """

    graph: Any
    intent: Any
    patch: Any
    manifests: Any
    resolved_targets: list[str]
    ambiguous: bool
    sandboxed: bool
    validation_passed: bool | None
    validation_skipped: bool
    dependency_conflicts: list[Any]
    package_only: bool = True


def _detect_engine_id(game_root: Path) -> str:
    """从游戏根目录判定引擎（决定探针分派与诚实分级）。"""
    if (game_root / "project.godot").exists():
        return "godot"
    if (game_root / "www" / "data" / "System.json").exists() or (
        game_root / "data" / "System.json"
    ).exists():
        return "rpgmv"
    return "miu2d"


def _contained_path(root: Path, name: str) -> Path:
    candidate = root / name
    if Path(name).is_absolute() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"artifact path escapes root: {name}")
    return candidate


def _file_hash(root: Path, name: str, *, prefix: str = "") -> dict[str, str]:
    return {
        "name": prefix + name,
        "sha256": hashlib.sha256(_contained_path(root, name).read_bytes()).hexdigest(),
    }


def _source_hashes(root: Path) -> list[dict[str, str]]:
    return [
        _file_hash(root, path.relative_to(root).as_posix())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _validate_staged_artifacts(
    patch: CDLPatch,
    files_dir: Path,
    original: Any,
    reviewed_files: dict[str, str],
) -> dict[str, Any]:
    staged = Miu2dClosedLoop(files_dir).perceive()
    checks: list[dict[str, Any]] = []
    actual_names = {
        path.relative_to(files_dir).as_posix() for path in files_dir.rglob("*") if path.is_file()
    }
    checks.append(
        {
            "name": "reviewed_file_inventory",
            "passed": actual_names == set(reviewed_files),
            "detail": "staged file paths exactly match approved review",
        }
    )
    for name, content in reviewed_files.items():
        checks.append(
            {
                "name": f"file_{name}_reviewed_bytes",
                "passed": _contained_path(files_dir, name).read_bytes() == content.encode("utf-8"),
                "detail": "staged bytes exactly match approved review",
            }
        )
    expected_properties: dict[str, dict[str, Any]] = {}
    for index, op in enumerate(patch.operations):
        node = staged.get_node(op.target_id)
        key = op.payload.get("key")
        expected = op.payload.get("value")
        passed = node is not None and key is not None and node.properties.get(key) == expected
        original_node = original.get_node(op.target_id)
        if original_node is not None and key is not None:
            expected_properties.setdefault(op.target_id, dict(original_node.properties))[key] = (
                expected
            )
        checks.append(
            {
                "name": f"operation_{index}_exact_value",
                "passed": passed,
                "detail": f"{op.target_id}.{key} == {expected!r}",
            }
        )
    staged_paths = {node.source_path for node in staged.nodes}
    for original_node in original.nodes:
        if original_node.source_path not in staged_paths:
            continue
        node = staged.get_node(original_node.id)
        expected_props = expected_properties.get(original_node.id, original_node.properties)
        checks.append(
            {
                "name": f"node_{original_node.id}_only_approved_changes",
                "passed": node is not None
                and _content_properties(node.properties) == _content_properties(expected_props),
                "detail": "staged properties match original plus reviewed operations",
            }
        )
    checks.append(
        {
            "name": "no_unplanned_nodes",
            "passed": all(original.get_node(node.id) is not None for node in staged.nodes),
            "detail": "staged files contain no additional entities",
        }
    )
    return {"passed": bool(checks) and all(check["passed"] for check in checks), "checks": checks}


def _content_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in properties.items()
        if key not in {"db_index", "source_order_domain"}
    }


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
