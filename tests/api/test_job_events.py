from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from udify.api.app import create_app
from udify.api.job_events import SSE_TERMINAL, _sse_event, job_events_stream
from udify.core.orchestration import JobStatus, JobStore
from udify.core.orchestration.mod_job import ModJob


@pytest.fixture
def store(tmp_path: Path) -> Iterator[JobStore]:
    result = JobStore(tmp_path / "jobs.db")
    yield result
    result.close()


def make_job(store: JobStore, status: JobStatus) -> ModJob:
    job = replace(ModJob.new("/tmp/game", "test", "/tmp/artifacts"), status=status)
    store.save(job)
    store.append_event(job.job_id, status.value, "job_created")
    return job


def test_sse_format() -> None:
    assert _sse_event({"a": 1}, event_id=42) == 'id: 42\nevent: job\ndata: {"a": 1}\n\n'


@pytest.mark.parametrize("status", list(SSE_TERMINAL))
def test_terminal_replays_canonical_log(store: JobStore, status: JobStatus) -> None:
    job = make_job(store, status)
    store.append_event(job.job_id, status.value, "finished")

    async def collect() -> list[str]:
        return [chunk async for chunk in job_events_stream(job.job_id, store)]

    chunks = asyncio.run(collect())
    expected = [_sse_event(e.to_dict(), event_id=e.seq) for e in store.events(job.job_id)]
    assert chunks[1:-1] == expected
    assert f'"status": "{status.value}"' in chunks[-1]
    assert '"seq": 2' in chunks[-1]


@pytest.mark.parametrize("status", [JobStatus.AWAITING_REVIEW, JobStatus.AWAITING_CLARIFICATION])
def test_waiting_states_stay_open(store: JobStore, status: JobStatus) -> None:
    job = make_job(store, status)

    async def collect() -> list[str]:
        stream = job_events_stream(job.job_id, store)
        try:
            return [await anext(stream) for _ in range(3)]
        finally:
            await stream.aclose()

    assert asyncio.run(collect())[-1] == ": ping\n\n"


def test_new_terminal_transition_is_not_missed(store: JobStore) -> None:
    job = make_job(store, JobStatus.AWAITING_REVIEW)

    async def collect() -> list[str]:
        stream = job_events_stream(job.job_id, store)
        chunks = [await anext(stream) for _ in range(3)]
        store.transition(job, JobStatus.REJECTED, event="review_rejected")
        chunks.extend([chunk async for chunk in stream])
        return chunks

    chunks = asyncio.run(collect())
    assert len([c for c in chunks if "event: job\n" in c]) == 2
    assert "review_rejected" in chunks[-2]
    assert "event: done" in chunks[-1]


def test_unknown_job_returns_404(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path / "state")) as client:
        response = client.get("/api/v0/jobs/unknown/events")
        assert response.status_code == 404
        assert "event: error" in response.text
