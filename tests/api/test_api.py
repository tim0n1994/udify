"""
批次 4B 测试：薄 API 契约（API-01..08）。

覆盖 ITERATION-PLAN-2026-08.md §6 批次 4B 验收：
- 统一信封与 DOMAIN_CATEGORY_DETAIL 错误码
- 创建任务 → 轮询到 awaiting_review → plan → approve → completed → package/report
- reject / rollback / 状态门 409 / 404
"""

from __future__ import annotations

import io
import json
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from udify.api.app import create_app
from udify.core.orchestration import JobStatus, JobStore
from udify.core.orchestration.mod_job import ModJob


@pytest.fixture
def game_root(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    root.mkdir()
    (root / "characters.ini").write_text(
        "[Boss]\nMaxLife=500\nAttack=50\nDefense=20\nDropRate=0.1\n"
        "[Hero]\nMaxLife=100\nAttack=15\nDefense=10\n"
    )
    (root / "items.ini").write_text("[Potion]\nType=heal\nValue=50\nPrice=20\n")
    return root


@pytest.fixture
def client(tmp_path: Path) -> Any:
    app = create_app(state_dir=tmp_path / "state")
    with TestClient(app) as c:
        yield c


def _wait_status(client: TestClient, job_id: str, target: str, timeout: float = 10.0) -> dict:
    """轮询直到 job 达到目标状态（后台线程驱动）。"""
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        r = client.get(f"/api/v0/jobs/{job_id}")
        assert r.status_code == 200
        last = r.json()["data"]["job"]
        if last["status"] == target:
            return last
        if last["status"] == "failed":
            raise AssertionError(f"job failed: {last['error']}")
        time.sleep(0.05)
    raise AssertionError(f"timeout waiting {target}, last={last.get('status')}")


class TestEnvelope:
    def test_healthz(self, client: TestClient) -> None:
        r = client.get("/api/v0/healthz")
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["error"] is None
        assert body["data"]["engines"]["miu2d"] is True

    def test_not_found_error_shape(self, client: TestClient) -> None:
        r = client.get("/api/v0/jobs/nonexistent")
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["code"] == "JOB_QUERY_NOT_FOUND"
        assert err["owner_module"]
        assert "suggested_action" in err

    def test_bad_game_root_400(self, client: TestClient) -> None:
        r = client.post(
            "/api/v0/jobs", json={"game_root": "/definitely/not/exist", "intent": "翻倍血量"}
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "JOB_INPUT_INVALID_GAME_ROOT"


class TestJobLifecycle:
    def test_full_flow(self, client: TestClient, game_root: Path) -> None:
        # 创建 → 202
        r = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "把Boss的血量翻倍"}
        )
        assert r.status_code == 202
        job = r.json()["data"]
        job_id = job["job_id"]

        # 轮询到人工门
        job = _wait_status(client, job_id, "awaiting_review")

        # 计划：操作 + diff + 静态验证 + 证据
        plan = client.get(f"/api/v0/jobs/{job_id}/plan").json()["data"]
        assert plan["operations"]
        assert plan["diffs"]
        assert "static_validation" in plan
        assert plan["graph_checksum"]

        # 时间线与审计链
        detail = client.get(f"/api/v0/jobs/{job_id}").json()["data"]
        assert detail["audit_chain_valid"] is True
        events = [e["event"] for e in detail["events"]]
        assert "job_created" in events
        assert "review_requested" in events

        # 批准 → 202 → 轮询 completed
        r = client.post(f"/api/v0/jobs/{job_id}/approve")
        assert r.status_code == 202
        job = _wait_status(client, job_id, "completed")

        # 报告
        report = client.get(f"/api/v0/jobs/{job_id}/report").json()["data"]
        assert "static_validation" in report
        assert "probe" in report

        # 包下载：合法 zip 且含 manifest/patch
        r = client.get(f"/api/v0/jobs/{job_id}/package")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "manifest.json" in zf.namelist()
        assert "patch.json" in zf.namelist()

        # 回滚 → rolled_back，包作废
        r = client.post(f"/api/v0/jobs/{job_id}/rollback")
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "rolled_back"
        assert client.get(f"/api/v0/jobs/{job_id}/package").status_code == 404

    def test_reject_flow(self, client: TestClient, game_root: Path) -> None:
        r = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "Boss掉落翻倍"}
        )
        job_id = r.json()["data"]["job_id"]
        _wait_status(client, job_id, "awaiting_review")

        r = client.post(f"/api/v0/jobs/{job_id}/reject", json={"reason": "先不改"})
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "rejected"

        # 终态后 approve → 409
        r = client.post(f"/api/v0/jobs/{job_id}/approve")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "JOB_STATE_INVALID_TRANSITION"

    def test_list_jobs(self, client: TestClient, game_root: Path) -> None:
        for intent in ("翻倍血量", "掉落翻倍"):
            client.post("/api/v0/jobs", json={"game_root": str(game_root), "intent": intent})
        r = client.get("/api/v0/jobs")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 2
        assert r.json()["meta"]["limit"] == 50

    def test_plan_not_ready_404(self, client: TestClient, game_root: Path) -> None:
        r = client.post("/api/v0/jobs", json={"game_root": str(game_root), "intent": "翻倍血量"})
        job_id = r.json()["data"]["job_id"]
        # 不等后台完成就查 report（plan 可能已好，report 一定没好）
        r = client.get(f"/api/v0/jobs/{job_id}/report")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "JOB_ARTIFACT_NOT_READY"
        assert r.json()["error"]["retryable"] is True

    def test_approve_before_review_409(self, client: TestClient, game_root: Path) -> None:
        job_id = client.app.state.udify.runner.create_job(str(game_root), "Boss血量翻倍").job_id
        r = client.post(f"/api/v0/jobs/{job_id}/approve")
        assert r.status_code == 409

    def test_events_incremental_pull(self, client: TestClient, game_root: Path) -> None:
        r = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "Boss血量翻倍"}
        )
        job_id = r.json()["data"]["job_id"]
        _wait_status(client, job_id, "awaiting_review")
        all_events = client.get(f"/api/v0/jobs/{job_id}").json()["data"]["events"]
        assert len(all_events) >= 3
        # 增量拉取：after_seq 之后只有新事件
        last_seq = all_events[-1]["seq"]
        rest = client.get(f"/api/v0/jobs/{job_id}?after_seq={last_seq}").json()["data"]["events"]
        assert rest == []

    def test_lifespan_waits_for_running_job_before_store_close(
        self, tmp_path: Path, game_root: Path
    ) -> None:
        """A running future may finish its final DB write before lifespan closes SQLite."""
        state_dir = tmp_path / "shutdown-state"
        app = create_app(state_dir=state_dir)
        state = app.state.udify
        started = threading.Event()

        def delayed_advance(job_id: str) -> None:
            started.set()
            time.sleep(0.08)
            state.store.append_event(job_id, "test", "shutdown_probe")

        state.runner.advance_to_review = delayed_advance
        with TestClient(app) as local_client:
            response = local_client.post(
                "/api/v0/jobs",
                json={"game_root": str(game_root), "intent": "翻倍血量"},
            )
            assert response.status_code == 202
            job_id = response.json()["data"]["job_id"]
            assert started.wait(timeout=5)

        reopened = JobStore(state_dir / "jobs.db")
        try:
            assert any(event.event == "shutdown_probe" for event in reopened.events(job_id))
        finally:
            reopened.close()


class TestModStack:
    def test_mods_list_and_conflicts(self, client: TestClient, game_root: Path) -> None:
        """MOD-STACK-03：两个改同一 Boss 的 Mod → 同 target 冲突被检出。"""
        ids = []
        for intent in ("把Boss的血量翻倍", "boss血量3倍"):
            r = client.post("/api/v0/jobs", json={"game_root": str(game_root), "intent": intent})
            job_id = r.json()["data"]["job_id"]
            _wait_status(client, job_id, "awaiting_review")
            client.post(f"/api/v0/jobs/{job_id}/approve")
            _wait_status(client, job_id, "completed")
            ids.append(job_id)

        data = client.get(f"/api/v0/mods?game_root={game_root}").json()["data"]
        assert len(data["mods"]) == 2
        assert len(data["conflicts"]) == 1
        assert set(data["conflicts"][0]["shared_targets"])


class TestOpenApi:
    def test_openapi_lists_all_endpoints(self, client: TestClient) -> None:
        spec = client.get("/api/openapi.json").json()
        paths = set(spec["paths"])
        expected = {
            "/api/v0/healthz",
            "/api/v0/jobs",
            "/api/v0/jobs/{job_id}",
            "/api/v0/jobs/{job_id}/plan",
            "/api/v0/jobs/{job_id}/approve",
            "/api/v0/jobs/{job_id}/reject",
            "/api/v0/jobs/{job_id}/report",
            "/api/v0/jobs/{job_id}/package",
            "/api/v0/jobs/{job_id}/rollback",
        }
        assert expected <= paths


class TestCanonicalApiSafety:
    def test_detail_does_not_mix_status_and_newer_events(
        self, client: TestClient, game_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        state = client.app.state.udify
        job = state.runner.create_job(str(game_root), "Boss血量翻倍")
        writer = JobStore(state.store.db_path)
        original_get = state.store.get
        committed = False

        def get_then_commit(job_id: str) -> ModJob | None:
            nonlocal committed
            snapshot = original_get(job_id)
            if not committed:
                writer.transition(job, JobStatus.FAILED, event="concurrent_failure")
                committed = True
            return snapshot

        monkeypatch.setattr(state.store, "get", get_then_commit)
        try:
            detail = client.get(f"/api/v0/jobs/{job.job_id}").json()["data"]
            assert committed
            assert detail["job"]["status"] == "created"
            assert [event["stage"] for event in detail["events"]] == ["created"]
            assert detail["audit_chain_valid"] is True
            head = detail["events"][-1]["seq"]
            next_detail = client.get(f"/api/v0/jobs/{job.job_id}?after_seq={head}").json()["data"]
            assert next_detail["job"]["status"] == "failed"
            assert [event["stage"] for event in next_detail["events"]] == ["failed"]
        finally:
            writer.close()

    def test_ambiguous_target_clarifies_then_completes(
        self, client: TestClient, game_root: Path
    ) -> None:
        original = (game_root / "characters.ini").read_bytes()
        response = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "血量翻倍"}
        )
        job_id = response.json()["data"]["job_id"]
        job = _wait_status(client, job_id, "awaiting_clarification")
        assert (game_root / "characters.ini").read_bytes() == original
        candidates = job["checkpoint"]["clarification"]["candidates"]
        assert len(candidates) >= 2
        selected = next(item["node_id"] for item in candidates if "Boss" in item["display_name"])
        assert client.post(f"/api/v0/jobs/{job_id}/approve").status_code == 409
        invalid = client.post(f"/api/v0/jobs/{job_id}/clarify", json={"target_ids": ["unknown"]})
        assert invalid.status_code == 400
        assert (
            client.get(f"/api/v0/jobs/{job_id}").json()["data"]["job"]["status"]
            == "awaiting_clarification"
        )
        response = client.post(f"/api/v0/jobs/{job_id}/clarify", json={"target_ids": [selected]})
        assert response.status_code == 202
        _wait_status(client, job_id, "awaiting_review")
        plan = client.get(f"/api/v0/jobs/{job_id}/plan").json()["data"]
        assert {op["target_id"] for op in plan["operations"]} == {selected}
        assert client.post(f"/api/v0/jobs/{job_id}/approve").status_code == 202
        _wait_status(client, job_id, "completed")
        assert (game_root / "characters.ini").read_bytes() == original
        stream = client.get(f"/api/v0/jobs/{job_id}/events")
        events = client.get(f"/api/v0/jobs/{job_id}").json()["data"]["events"]
        frames = [frame for frame in stream.text.split("\n\n") if "event: job\n" in frame]
        assert [json.loads(frame.split("data: ", 1)[1]) for frame in frames] == events

    def test_clarification_can_be_rejected(self, client: TestClient, game_root: Path) -> None:
        response = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "血量翻倍"}
        )
        job_id = response.json()["data"]["job_id"]
        _wait_status(client, job_id, "awaiting_clarification")
        response = client.post(f"/api/v0/jobs/{job_id}/reject")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "rejected"

    def test_tampered_audit_blocks_approval(self, client: TestClient, game_root: Path) -> None:
        response = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "Boss血量翻倍"}
        )
        job_id = response.json()["data"]["job_id"]
        _wait_status(client, job_id, "awaiting_review")
        with sqlite3.connect(client.app.state.udify.state_dir / "jobs.db") as db:
            db.execute(
                "UPDATE job_events SET event = 'tampered' WHERE job_id = ? AND seq = 1", (job_id,)
            )
        response = client.post(f"/api/v0/jobs/{job_id}/approve")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "JOB_AUDIT_INVALID"
        assert (
            client.get(f"/api/v0/jobs/{job_id}").json()["data"]["job"]["status"]
            == "awaiting_review"
        )

    def test_package_denied_when_failed_even_if_path_exists(
        self, client: TestClient, game_root: Path, tmp_path: Path
    ) -> None:
        state = client.app.state.udify
        job = state.runner.create_job(str(game_root), "Boss血量翻倍")
        package = tmp_path / "stale.zip"
        package.write_bytes(b"stale")
        state.store.transition(
            job, JobStatus.FAILED, event="failed", checkpoint_update={"package": str(package)}
        )
        assert client.get(f"/api/v0/jobs/{job.job_id}/package").status_code == 404

    def test_unhandled_background_failure_is_persisted(
        self, client: TestClient, game_root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(job_id: str) -> None:
            raise OSError("disk unavailable")

        monkeypatch.setattr(client.app.state.udify.runner, "advance_to_review", fail)
        response = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "Boss血量翻倍"}
        )
        job = _wait_status(client, response.json()["data"]["job_id"], "failed")
        assert job["error"]["code"] == "JOB_ARTIFACT_IO_FAILED"

    def test_package_tampering_denied(self, client: TestClient, game_root: Path) -> None:
        response = client.post(
            "/api/v0/jobs", json={"game_root": str(game_root), "intent": "Boss血量翻倍"}
        )
        job_id = response.json()["data"]["job_id"]
        _wait_status(client, job_id, "awaiting_review")
        assert client.post(f"/api/v0/jobs/{job_id}/approve").status_code == 202
        job = _wait_status(client, job_id, "completed")
        assert job["checkpoint"]["package_sha256"]
        Path(job["checkpoint"]["package"]).write_bytes(b"corrupted package")
        response = client.get(f"/api/v0/jobs/{job_id}/package")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "JOB_PACKAGE_INTEGRITY_FAILED"

    def test_compensating_job_is_recovered(self, tmp_path: Path, game_root: Path) -> None:
        state_dir = tmp_path / "recovery"
        app = create_app(state_dir)
        state = app.state.udify
        job = state.runner.create_job(str(game_root), "Boss血量翻倍")
        job = state.store.transition(job, JobStatus.FAILED, event="failed")
        state.store.transition(job, JobStatus.COMPENSATING, event="rollback_started")
        with TestClient(app) as recovery_client:
            _wait_status(recovery_client, job.job_id, "rolled_back")

    @pytest.mark.parametrize("action", ["reject", "approve", "rollback"])
    def test_mutations_respect_exclusive_job_guard(
        self, client: TestClient, game_root: Path, action: str
    ) -> None:
        state = client.app.state.udify
        job = state.runner.create_job(str(game_root), "Boss血量翻倍")
        state.runner.advance_to_review(job.job_id)
        state.inflight.add(job.job_id)
        try:
            response = client.post(f"/api/v0/jobs/{job.job_id}/{action}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "JOB_STATE_BUSY"
        finally:
            state.inflight.discard(job.job_id)

    @pytest.mark.parametrize("origin", ["http://localhost:41239", "http://127.0.0.1:49812"])
    def test_loopback_development_origins(self, client: TestClient, origin: str) -> None:
        response = client.options(
            "/api/v0/jobs", headers={"Origin": origin, "Access-Control-Request-Method": "POST"}
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin

    def test_remote_origin_denied(self, client: TestClient) -> None:
        response = client.options(
            "/api/v0/jobs",
            headers={"Origin": "http://example.com:3000", "Access-Control-Request-Method": "POST"},
        )
        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers
