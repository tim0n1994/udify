import hashlib
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from udify.core.execution.vfs import VirtualFileSystem
from udify.core.orchestration import JobInputError, JobRunner, JobStatus, JobStore
from udify.models.cdl_patch import CDLPatch


@pytest.fixture
def setup(tmp_path: Path) -> Iterator[tuple[Path, JobStore, JobRunner]]:
    root = tmp_path / "game"
    root.mkdir()
    (root / "characters.ini").write_text("[Boss]\nMaxLife=500\nAttack=50\n")
    store = JobStore(tmp_path / "jobs.db")
    yield root, store, JobRunner(store, tmp_path / "artifacts")
    store.close()


def test_static_package_report_never_claims_runtime_or_install(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    runner.advance_to_review(job.job_id)
    job = runner.approve(job.job_id)
    assert job.status == JobStatus.COMPLETED
    report = json.loads(Path(job.artifacts_dir, "report.json").read_text())
    assert report["delivery"]["installed"] is False
    assert report["delivery"]["tier"] == "STATIC_ONLY"
    assert report["artifact_validation"]["passed"] is True
    assert report["probe"]["game_started"] is False
    assert report["probe"]["state_readable"] is False
    assert report["probe"]["skipped"] is True
    assert all(
        "runtime validation passed" not in g["evidence"] for g in report["gate_verdict"]["gates"]
    )
    assert "MaxLife=500" in (root / "characters.ini").read_text()
    assert "MaxLife=1000" in Path(job.artifacts_dir, "files/characters.ini").read_text()


@pytest.mark.parametrize("name", ["patch.json", "plan.json"])
def test_reviewed_artifact_tampering_is_blocked(
    setup: tuple[Path, JobStore, JobRunner], name: str
) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    job = runner.advance_to_review(job.job_id)
    path = Path(job.artifacts_dir, name)
    data = json.loads(path.read_text())
    data["intent"] = "tampered"
    path.write_text(json.dumps(data))
    job = runner.approve(job.job_id)
    assert job.status == JobStatus.FAILED
    assert job.error.code == "JOB_APPROVAL_INTEGRITY_FAILED"


def test_original_bytes_drift_even_when_graph_unchanged_is_blocked(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    runner.advance_to_review(job.job_id)
    source = root / "characters.ini"
    source.write_text(source.read_text() + "; external comment\n")
    job = runner.approve(job.job_id)
    assert job.status == JobStatus.FAILED
    assert job.error.code == "JOB_APPROVAL_INTEGRITY_FAILED"


@pytest.mark.parametrize("marker", ["project.godot", "data/System.json"])
def test_unsupported_engine_rejected_at_create(
    setup: tuple[Path, JobStore, JobRunner], marker: str
) -> None:
    root, store, runner = setup
    path = root / marker
    path.parent.mkdir(exist_ok=True)
    path.write_text("{}")
    with pytest.raises(JobInputError) as exc:
        runner.create_job(str(root), "Boss血量翻倍")
    assert exc.value.error.code == "JOB_INPUT_UNSUPPORTED_ENGINE"


def test_compensating_is_recovered_idempotently(setup: tuple[Path, JobStore, JobRunner]) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    runner.advance_to_review(job.job_id)
    job = runner.approve(job.job_id)
    package = Path(job.checkpoint["package"])
    store.transition(job, JobStatus.COMPENSATING, event="rollback_started")
    package.rename(package.with_suffix(".zip.rolled_back"))
    recovered = runner.recover_incomplete()
    assert len(recovered) == 1
    assert recovered[0].status == JobStatus.ROLLED_BACK
    assert Path(recovered[0].checkpoint["package_revoked"]).exists()


def test_corrupt_patch_becomes_durable_failure(setup: tuple[Path, JobStore, JobRunner]) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    job = runner.advance_to_review(job.job_id)
    Path(job.artifacts_dir, "patch.json").write_text("{broken")
    assert runner.approve(job.job_id).status == JobStatus.FAILED


def test_clarification_survives_restart_and_selects_only_one_target(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    (root / "characters.ini").write_text("[BossA]\nMaxLife=500\n[BossB]\nMaxLife=800\n")
    job = runner.create_job(str(root), "Boss血量翻倍")
    waiting = runner.advance_to_review(job.job_id)
    assert waiting.status == JobStatus.AWAITING_CLARIFICATION
    runner = JobRunner(store, Path(waiting.artifacts_dir).parent)
    assert runner.resume(job.job_id) == waiting
    candidate = waiting.checkpoint["clarification"]["candidates"][0]["node_id"]
    with pytest.raises(JobInputError):
        runner.clarify(job.job_id, ["unknown"])
    assert store.get(job.job_id).status == JobStatus.AWAITING_CLARIFICATION
    review = runner.clarify(job.job_id, [candidate])
    assert review.status == JobStatus.AWAITING_REVIEW
    patch = json.loads(Path(review.artifacts_dir, "patch.json").read_text())
    assert {op["target_id"] for op in patch["operations"]} == {candidate}
    assert runner.approve(job.job_id).status == JobStatus.COMPLETED


def test_clarification_rejects_source_drift_without_state_change(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    source = root / "characters.ini"
    source.write_text("[BossA]\nMaxLife=500\n[BossB]\nMaxLife=800\n")
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    candidate = job.checkpoint["clarification"]["candidates"][0]["node_id"]
    source.write_text(source.read_text() + "; changed\n")
    with pytest.raises(JobInputError) as exc:
        runner.clarify(job.job_id, [candidate])
    assert exc.value.error.code == "JOB_GRAPH_VERSION_MISMATCH"
    assert store.get(job.job_id).status == JobStatus.AWAITING_CLARIFICATION


def test_replanning_updates_checksum_after_crash(setup: tuple[Path, JobStore, JobRunner]) -> None:
    root, store, runner = setup
    job = runner.create_job(str(root), "Boss血量翻倍")
    job = store.transition(job, JobStatus.PERCEIVING, event="started")
    store.transition(
        job, JobStatus.PLANNING, event="started", checkpoint_update={"graph_checksum": "old"}
    )
    review = runner.resume(job.job_id)
    assert review.checkpoint["graph_checksum"] != "old"
    assert runner.approve(job.job_id).status == JobStatus.COMPLETED


def test_audit_chain_tamper_blocks_approval(setup: tuple[Path, JobStore, JobRunner]) -> None:
    root, store, runner = setup
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    store._conn.execute("UPDATE job_events SET payload_json = '{}' WHERE seq = 1")
    store._conn.commit()
    failed = runner.approve(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error.code == "JOB_APPROVAL_INTEGRITY_FAILED"


def test_rollback_does_not_claim_originals_restored_after_external_change(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    job = runner.approve(job.job_id)
    (root / "characters.ini").write_text("[Boss]\nMaxLife=999\n")
    revoked = runner.rollback(job.job_id)
    assert revoked.status == JobStatus.ROLLED_BACK
    assert revoked.checkpoint["rollback"]["checksum_intact"] is False
    assert not Path(job.checkpoint["package"]).exists()


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_package_preserves_non_target_bytes_and_binds_hash(
    setup: tuple[Path, JobStore, JobRunner],
    newline: bytes,
) -> None:
    root, store, runner = setup
    original = newline.join(
        [
            b"; preserved comment",
            b"[Boss]",
            b"MaxLife=500",
            b"Attack=50",
            b"[Hero]",
            b"MaxLife=100",
            b"",
        ]
    )
    source = root / "characters.ini"
    source.write_bytes(original)
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    job = runner.approve(job.job_id)
    assert job.status == JobStatus.COMPLETED
    package = Path(job.checkpoint["package"])
    assert hashlib.sha256(package.read_bytes()).hexdigest() == job.checkpoint["package_sha256"]
    with zipfile.ZipFile(package) as archive:
        assert archive.read("files/characters.ini") == original.replace(
            b"MaxLife=500", b"MaxLife=1000"
        )
    assert source.read_bytes() == original


def test_artifact_validator_blocks_executor_changing_unreviewed_property(
    setup: tuple[Path, JobStore, JobRunner],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from udify.core.miu2d_pipeline import Miu2dClosedLoop

    root, store, runner = setup
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    real_preview = Miu2dClosedLoop.preview

    def corrupt_preview(
        self: Miu2dClosedLoop,
        patch: CDLPatch,
    ) -> tuple[VirtualFileSystem, list[str], str | None]:
        vfs, errors, fatal = real_preview(self, patch)
        content = vfs.read_file("characters.ini")
        assert content is not None
        vfs.write_file("characters.ini", content.replace("Attack=50", "Attack=999"))
        return vfs, errors, fatal

    monkeypatch.setattr(Miu2dClosedLoop, "preview", corrupt_preview)
    failed = runner.approve(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error.code == "JOB_ARTIFACT_VALIDATION_FAILED"
    assert not list(Path(failed.artifacts_dir).glob("*.zip"))


def test_missing_patch_becomes_durable_failure(setup: tuple[Path, JobStore, JobRunner]) -> None:
    root, store, runner = setup
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    Path(job.artifacts_dir, "patch.json").unlink()
    failed = runner.approve(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error.code == "JOB_ARTIFACT_IO_FAILED"


def test_artifacts_inside_game_root_are_rejected_before_writes(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    runner = JobRunner(store, root / ".udify" / "jobs")
    before = sorted(root.rglob("*"))
    with pytest.raises(JobInputError) as exc:
        runner.create_job(str(root), "Boss血量翻倍")
    assert exc.value.error.code == "JOB_INPUT_OUTPUT_OVERLAP"
    assert sorted(root.rglob("*")) == before


def test_single_modified_file_in_multifile_game_packages_successfully(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    (root / "aaa.ini").write_text("[Hero]\nMaxLife=100\n")
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    assert runner.approve(job.job_id).status == JobStatus.COMPLETED


def test_staging_symlink_cannot_redirect_writes_into_game(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    source = root / "characters.ini"
    before = source.read_bytes()
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    Path(job.artifacts_dir, "files").symlink_to(root, target_is_directory=True)
    assert runner.approve(job.job_id).status == JobStatus.FAILED
    assert source.read_bytes() == before


def test_database_inside_game_root_rejected_without_job_write(
    setup: tuple[Path, JobStore, JobRunner],
    tmp_path: Path,
) -> None:
    root, store, runner = setup
    nested = JobStore(root / "state.db")
    try:
        runner = JobRunner(nested, tmp_path / "outside")
        with pytest.raises(JobInputError) as exc:
            runner.create_job(str(root), "Boss血量翻倍")
        assert exc.value.error.code == "JOB_INPUT_OUTPUT_OVERLAP"
        assert nested.list_jobs() == []
    finally:
        nested.close()


@pytest.mark.parametrize("fault", ["comment", "extra_file"])
def test_unreviewed_output_bytes_or_files_block_delivery(
    setup: tuple[Path, JobStore, JobRunner],
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    from udify.core.miu2d_pipeline import Miu2dClosedLoop

    root, store, runner = setup
    source = root / "characters.ini"
    source.write_text("; approved comment\n" + source.read_text())
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    real_preview = Miu2dClosedLoop.preview

    def corrupt_preview(
        self: Miu2dClosedLoop, patch: CDLPatch
    ) -> tuple[VirtualFileSystem, list[str], str | None]:
        vfs, errors, fatal = real_preview(self, patch)
        if fault == "comment":
            content = vfs.read_file("characters.ini")
            assert content is not None
            vfs.write_file("characters.ini", content.replace("; approved comment\n", ""))
        else:
            vfs.write_file("zzz.bin", "unexpected file")
        return vfs, errors, fatal

    monkeypatch.setattr(Miu2dClosedLoop, "preview", corrupt_preview)
    failed = runner.approve(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error.code == "JOB_ARTIFACT_VALIDATION_FAILED"


def test_deleted_source_does_not_block_package_revocation(
    setup: tuple[Path, JobStore, JobRunner],
) -> None:
    root, store, runner = setup
    job = runner.advance_to_review(runner.create_job(str(root), "Boss血量翻倍").job_id)
    job = runner.approve(job.job_id)
    root.rename(root.with_name("moved_game"))
    revoked = runner.rollback(job.job_id)
    assert revoked.status == JobStatus.ROLLED_BACK
    assert revoked.checkpoint["rollback"]["checksum_intact"] is None
    assert not Path(job.checkpoint["package"]).exists()
    assert Path(revoked.checkpoint["package_revoked"]).exists()
