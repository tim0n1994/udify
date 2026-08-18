"""iter4 M4 PR2 — SSE 进度事件流测试（T4-STREAMING-UX 研究落地）。

覆盖：历史重放、心跳、终态关闭、job not found、after_seq 增量。
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from udify.api.app import create_app
from udify.api.job_events import SSE_TERMINAL, _sse_event, job_events_stream
from udify.core.orchestration import JobStatus, JobStore
from udify.core.orchestration.mod_job import ModJob
from udify.core.orchestration.progress import ProgressEvent, ProgressStage, ProgressStore


@pytest.fixture
def progress_store(tmp_path: Path) -> ProgressStore:
    return ProgressStore(str(tmp_path / "progress.db"))


@pytest.fixture
def job_store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.db")


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(state_dir=tmp_path / "state")
    return TestClient(app)


def _make_job(store: JobStore, job_id: str, status: JobStatus = JobStatus.CREATED) -> ModJob:
    """直接造一个 job 记录到 store。"""
    base = ModJob.new(game_root="/tmp/game", intent="测试", artifacts_dir="/tmp/artifacts")
    job = dataclasses.replace(base, job_id=job_id, status=status)
    store.save(job)
    return job


# --------------------------------------------------------------- pure formatting


class TestSSEFormatting:
    def test_sse_event_has_event_and_data(self):
        out = _sse_event({"stage": "planning", "pct": 50.0})
        assert out.startswith("event: progress\n")
        assert "data:" in out
        assert out.endswith("\n\n")

    def test_sse_event_custom_event_type(self):
        out = _sse_event({"status": "completed"}, event="done")
        assert out.startswith("event: done\n")
        data_line = [ln for ln in out.split("\n") if ln.startswith("data:")][0]
        assert json.loads(data_line[len("data:") :].strip())["status"] == "completed"

    def test_sse_terminal_includes_completed_and_failed(self):
        assert JobStatus.COMPLETED in SSE_TERMINAL
        assert JobStatus.FAILED in SSE_TERMINAL
        assert JobStatus.REJECTED in SSE_TERMINAL


# --------------------------------------------------------------- stream behavior


def _run_stream(coro):
    """同步跑完一个 async generator，收集所有 chunk。"""

    async def _collect():
        chunks = []
        async for c in coro:
            chunks.append(c)
        return chunks

    return asyncio.run(_collect())


class TestJobEventsStream:
    def test_replays_history_then_closes_on_terminal(self, job_store, progress_store):
        """有历史事件 + 任务已终态 → 重放后立刻关闭。"""
        _make_job(job_store, "job-1", JobStatus.COMPLETED)
        progress_store.append(
            ProgressEvent("job-1", ProgressStage.PERCEIVING, seq=1, current=5, total=10)
        )
        progress_store.append(
            ProgressEvent("job-1", ProgressStage.PLANNING, seq=2, current=3, total=5)
        )

        chunks = _run_stream(job_events_stream("job-1", job_store, progress_store))

        # 重放了两个历史事件
        progress_chunks = [c for c in chunks if "event: progress" in c]
        assert len(progress_chunks) == 2
        # 终态推送了 done 事件
        done_chunks = [c for c in chunks if "event: done" in c]
        assert len(done_chunks) == 1
        assert "completed" in done_chunks[0]

    def test_stream_closes_on_failed(self, job_store, progress_store):
        _make_job(job_store, "job-2", JobStatus.FAILED)
        chunks = _run_stream(job_events_stream("job-2", job_store, progress_store))
        done = [c for c in chunks if "event: done" in c]
        assert len(done) == 1
        assert "failed" in done[0]

    def test_non_terminal_streams_heartbeat_then_events(self, job_store, progress_store):
        """非终态任务：先推心跳，后有新事件时推送。"""
        _make_job(job_store, "job-3", JobStatus.PERCEIVING)
        progress_store.append(ProgressEvent("job-3", ProgressStage.PERCEIVING, seq=1))

        # 由于非终态会无限循环，用 asyncio.run + 先取 N 条再取消
        async def _take_n(n):
            out = []
            async for c in job_events_stream("job-3", job_store, progress_store):
                out.append(c)
                if len(out) >= n:
                    break
            return out

        chunks = asyncio.run(_take_n(3))
        # 第一条是历史重放（progress 事件）
        assert any("event: progress" in c for c in chunks)
        # 有心跳
        assert any(": ping" in c for c in chunks)

    def test_after_seq_skips_old_events(self, job_store, progress_store):
        """after_seq=N 只重放 seq>N 的事件。"""
        _make_job(job_store, "job-4", JobStatus.COMPLETED)
        progress_store.append(ProgressEvent("job-4", ProgressStage.PERCEIVING, seq=1))
        progress_store.append(ProgressEvent("job-4", ProgressStage.PLANNING, seq=2))
        progress_store.append(ProgressEvent("job-4", ProgressStage.VALIDATING, seq=3))

        chunks = _run_stream(job_events_stream("job-4", job_store, progress_store, after_seq=1))
        progress_chunks = [c for c in chunks if "event: progress" in c]
        # 只重放 seq=2 和 seq=3
        assert len(progress_chunks) == 2

    def test_no_history_terminal_immediately_done(self, job_store, progress_store):
        """无历史 + 已终态 → 直接 done。"""
        _make_job(job_store, "job-5", JobStatus.COMPLETED)
        chunks = _run_stream(job_events_stream("job-5", job_store, progress_store))
        progress_chunks = [c for c in chunks if "event: progress" in c]
        assert len(progress_chunks) == 0
        done = [c for c in chunks if "event: done" in c]
        assert len(done) == 1


# --------------------------------------------------------------- HTTP route


class TestSSERoute:
    def test_route_returns_404_for_unknown_job(self, client):
        with client.stream("GET", "/api/v0/jobs/nonexistent/events") as resp:
            assert resp.status_code == 404
            body = b"".join(resp.iter_bytes()).decode()
            assert "error" in body

    def test_route_registered_and_returns_event_stream(self, client, tmp_path):
        """路由已注册，对存在的 job 返回 text/event-stream。"""
        # 造一个 job
        state = client.app.state.udify
        game = tmp_path / "game"
        game.mkdir()
        job = state.runner.create_job(str(game), "测试")
        # 迁移到终态（completed），让流自然结束而非无限挂起
        import dataclasses  # noqa: PLC0415

        state.store.save(dataclasses.replace(job, status=JobStatus.COMPLETED))
        with client.stream("GET", f"/api/v0/jobs/{job.job_id}/events") as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            # 终态流会重放历史（空）后立刻推送 done 并关闭
            body = b"".join(resp.iter_bytes()).decode()
            assert "event: done" in body
            assert "completed" in body
