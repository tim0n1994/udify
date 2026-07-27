"""
批次 4A 测试：ModJob 状态机 + SQLite JobStore + JobRunner。

覆盖 ITERATION-PLAN-2026-08.md §6 批次 4A 的验收：
- 4A-1 非法迁移抛错、全部合法迁移路径
- 4A-2 崩溃模拟（重开库不丢已提交数据）
- 4A-3 checkpoint 恢复、审计链 verify、篡改检测
- 4A-4 dry-run 全流程事件序列、kill 后恢复、图漂移守卫
"""

from __future__ import annotations

from pathlib import Path

import pytest

from udify.core.orchestration import (
    ALLOWED_TRANSITIONS,
    InvalidTransitionError,
    JobError,
    JobInputError,
    JobRunner,
    JobStatus,
    JobStore,
    ModJob,
)


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "characters.ini").write_text(
        "[Boss]\nMaxLife=500\nAttack=50\nDefense=20\nDropRate=0.1\n"
        "[Hero]\nMaxLife=100\nAttack=15\nDefense=10\n"
    )
    (root / "items.ini").write_text(
        "[Potion]\nType=heal\nValue=50\nPrice=20\n[Sword]\nType=weapon\nAttack=20\nPrice=100\n"
    )
    return root


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "state" / "jobs.db")


@pytest.fixture
def runner(store: JobStore, tmp_path: Path) -> JobRunner:
    return JobRunner(store, tmp_path / "artifacts")


# === 4A-1 状态机 =============================================================


class TestModJobStateMachine:
    def test_new_job_starts_created(self) -> None:
        job = ModJob.new("/g", "翻倍血量", "/a")
        assert job.status == JobStatus.CREATED
        assert len(job.job_id) == 12

    @pytest.mark.parametrize(
        ("current", "target"),
        [(src, dst) for src, targets in ALLOWED_TRANSITIONS.items() for dst in targets],
    )
    def test_all_legal_transitions(self, current: JobStatus, target: JobStatus) -> None:
        job = ModJob.new("/g", "i", "/a")
        object.__setattr__(job, "status", current)
        moved = job.with_status(
            target,
            error=JobError("X_Y_Z", "m", "t") if target == JobStatus.FAILED else None,
        )
        assert moved.status == target
        assert moved is not job  # 不可变：新实例

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (JobStatus.CREATED, JobStatus.COMPLETED),
            (JobStatus.AWAITING_REVIEW, JobStatus.PACKAGING),
            (JobStatus.REJECTED, JobStatus.APPLYING),
            (JobStatus.ROLLED_BACK, JobStatus.CREATED),
            (JobStatus.COMPLETED, JobStatus.APPLYING),
        ],
    )
    def test_illegal_transitions_raise(self, current: JobStatus, target: JobStatus) -> None:
        job = ModJob.new("/g", "i", "/a")
        object.__setattr__(job, "status", current)
        with pytest.raises(InvalidTransitionError) as exc:
            job.with_status(target)
        assert exc.value.code == "JOB_STATE_INVALID_TRANSITION"

    def test_serde_round_trip(self) -> None:
        job = ModJob.new("/g", "让Boss更难", "/a")
        job = job.with_status(JobStatus.PERCEIVING, checkpoint_update={"k": "v"})
        restored = ModJob.from_dict(job.to_dict())
        assert restored == job

    def test_error_serde(self) -> None:
        err = JobError(
            "JOB_PLAN_EMPTY", "无法生成计划", "runner", retryable=False, suggested_action="换个说法"
        )
        assert JobError.from_dict(err.to_dict()) == err


# === 4A-2/4A-3 JobStore ======================================================


class TestJobStore:
    def test_save_get_round_trip(self, store: JobStore) -> None:
        job = ModJob.new("/g", "i", "/a")
        store.save(job)
        assert store.get(job.job_id) == job

    def test_get_missing_returns_none(self, store: JobStore) -> None:
        assert store.get("nope") is None

    def test_list_ordered_desc(self, store: JobStore) -> None:
        jobs = [ModJob.new("/g", f"i{n}", "/a") for n in range(3)]
        for j in jobs:
            store.save(j)
        listed = store.list_jobs()
        assert [j.job_id for j in listed] == [j.job_id for j in reversed(jobs)]

    def test_durable_across_reopen(self, tmp_path: Path) -> None:
        db = tmp_path / "jobs.db"
        s1 = JobStore(db)
        job = ModJob.new("/g", "i", "/a")
        s1.save(job)
        s1.append_event(job.job_id, "created", "job_created")
        s1.close()

        s2 = JobStore(db)
        assert s2.get(job.job_id) == job
        assert len(s2.events(job.job_id)) == 1
        assert s2.verify_chain(job.job_id)

    def test_event_chain_verify_and_tamper(self, store: JobStore) -> None:
        job = ModJob.new("/g", "i", "/a")
        store.save(job)
        for n in range(3):
            store.append_event(job.job_id, "s", f"e{n}", {"n": n})
        assert store.verify_chain(job.job_id)

        # 篡改中间一条 payload → 链断裂
        store._conn.execute(  # noqa: SLF001 测试故意直捣数据库
            "UPDATE job_events SET payload_json = ? WHERE seq = 2", ('{"n": 999}',)
        )
        store._conn.commit()
        assert not store.verify_chain(job.job_id)

    def test_transition_atomically_saves_and_logs(self, store: JobStore) -> None:
        job = ModJob.new("/g", "i", "/a")
        store.save(job)
        moved = store.transition(job, JobStatus.PERCEIVING, event="stage_started")
        assert store.get(job.job_id) is not None
        assert store.get(job.job_id).status == JobStatus.PERCEIVING  # type: ignore[union-attr]
        events = store.events(job.job_id)
        assert events[-1].event == "stage_started"
        assert events[-1].payload["to"] == "perceiving"
        assert moved.status == JobStatus.PERCEIVING

    def test_transition_rejects_illegal(self, store: JobStore) -> None:
        job = ModJob.new("/g", "i", "/a")
        store.save(job)
        with pytest.raises(InvalidTransitionError):
            store.transition(job, JobStatus.COMPLETED, event="nope")


# === 4A-4 JobRunner 全流程 ====================================================


class TestJobRunnerHappyPath:
    def test_full_flow_to_completed(
        self, runner: JobRunner, store: JobStore, game_root: Path
    ) -> None:
        job = runner.create_job(str(game_root), "把Boss的血量翻倍")
        assert job.status == JobStatus.CREATED

        job = runner.advance_to_review(job.job_id)
        assert job.status == JobStatus.AWAITING_REVIEW
        artifacts = Path(job.artifacts_dir)
        assert (artifacts / "graph.json").exists()
        assert (artifacts / "patch.json").exists()
        assert (artifacts / "plan.json").exists()
        assert job.checkpoint["graph_checksum"]

        job = runner.approve(job.job_id)
        assert job.status == JobStatus.COMPLETED
        assert (artifacts / "report.json").exists()
        package = Path(job.checkpoint["package"])
        assert package.exists() and package.suffix == ".zip"

        # 原文件未被修改（红线：永不写 game_root）
        assert "MaxLife=500" in (game_root / "characters.ini").read_text()

        # 事件链完整且可回放
        assert store.verify_chain(job.job_id)
        events = [e.event for e in store.events(job.job_id)]
        assert events[0] == "job_created"
        assert "review_requested" in events
        assert "approved" in events
        assert events[-1] == "job_completed"

    def test_reject_flow(self, runner: JobRunner, game_root: Path) -> None:
        job = runner.create_job(str(game_root), "翻倍血量")
        runner.advance_to_review(job.job_id)
        job = runner.reject(job.job_id, reason="不想改了")
        assert job.status == JobStatus.REJECTED
        with pytest.raises(JobInputError):
            runner.approve(job.job_id)

    def test_rollback_after_completed(self, runner: JobRunner, game_root: Path) -> None:
        job = runner.create_job(str(game_root), "翻倍血量")
        runner.advance_to_review(job.job_id)
        job = runner.approve(job.job_id)
        package = Path(job.checkpoint["package"])

        job = runner.rollback(job.job_id)
        assert job.status == JobStatus.ROLLED_BACK
        assert not package.exists()  # 包已作废（改名）
        assert Path(job.checkpoint["package_revoked"]).exists()
        # checksum 完整性在事件里留档
        events = runner._store.events(job.job_id)  # noqa: SLF001
        rolled = [e for e in events if e.event == "rolled_back"][0]
        assert rolled.payload["checksum_intact"] is True


class TestJobRunnerGuards:
    def test_invalid_game_root(self, runner: JobRunner) -> None:
        with pytest.raises(JobInputError) as exc:
            runner.create_job("/definitely/not/exist", "i")
        assert exc.value.error.code == "JOB_INPUT_INVALID_GAME_ROOT"

    def test_empty_intent(self, runner: JobRunner, game_root: Path) -> None:
        with pytest.raises(JobInputError) as exc:
            runner.create_job(str(game_root), "   ")
        assert exc.value.error.code == "JOB_INPUT_EMPTY_INTENT"

    def test_unplannable_intent_fails_with_error(self, runner: JobRunner, game_root: Path) -> None:
        job = runner.create_job(str(game_root), "呜啦啦啦完全无法理解的东西xyzzy")
        job = runner.advance_to_review(job.job_id)
        assert job.status == JobStatus.FAILED
        assert job.error is not None
        assert job.error.code == "JOB_PLAN_EMPTY"

    def test_graph_drift_rejected_on_approve(self, runner: JobRunner, game_root: Path) -> None:
        """工业契约：审阅后游戏文件变化 → 拒绝应用，不允许"尽量应用"。"""
        job = runner.create_job(str(game_root), "把Boss的血量翻倍")
        runner.advance_to_review(job.job_id)
        # 审阅期间游戏文件被外部修改
        (game_root / "characters.ini").write_text("[Boss]\nMaxLife=777\n")
        job = runner.approve(job.job_id)
        assert job.status == JobStatus.FAILED
        assert job.error is not None
        assert job.error.code == "JOB_GRAPH_VERSION_MISMATCH"


class TestJobRunnerRecovery:
    def test_resume_from_perceiving_after_crash(
        self, store: JobStore, runner: JobRunner, game_root: Path
    ) -> None:
        """kill -9 模拟：状态停在 perceiving，重启后 resume 推进到 awaiting_review。"""
        job = runner.create_job(str(game_root), "把Boss的血量翻倍")
        # 手工把 job 推到 perceiving 后"崩溃"（不再继续）
        store.transition(job, JobStatus.PERCEIVING, event="stage_started")

        resumed = runner.resume(job.job_id)
        assert resumed.status == JobStatus.AWAITING_REVIEW
        assert Path(resumed.artifacts_dir, "plan.json").exists()

    def test_recover_incomplete_scans_all(
        self, store: JobStore, runner: JobRunner, game_root: Path
    ) -> None:
        j1 = runner.create_job(str(game_root), "翻倍血量")
        store.transition(j1, JobStatus.PERCEIVING, event="stage_started")
        runner.create_job(str(game_root), "掉落翻倍")  # 停在 created

        recovered = runner.recover_incomplete()
        assert {j.status for j in recovered} == {JobStatus.AWAITING_REVIEW}
        assert len(recovered) == 2

    def test_awaiting_review_survives_reopen(self, tmp_path: Path, game_root: Path) -> None:
        """durable 判据：重开 store 后人工门状态原样恢复，可直接 approve。"""
        db = tmp_path / "s" / "jobs.db"
        s1 = JobStore(db)
        r1 = JobRunner(s1, tmp_path / "art")
        job = r1.create_job(str(game_root), "把Boss的血量翻倍")
        r1.advance_to_review(job.job_id)
        s1.close()

        s2 = JobStore(db)
        r2 = JobRunner(s2, tmp_path / "art")
        restored = s2.get(job.job_id)
        assert restored is not None
        assert restored.status == JobStatus.AWAITING_REVIEW
        done = r2.approve(job.job_id)
        assert done.status == JobStatus.COMPLETED
        assert s2.verify_chain(job.job_id)
