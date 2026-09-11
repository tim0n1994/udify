from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from udify.api.app import create_app
from udify.core.orchestration import JobStatus


@pytest.fixture
def completed_client(tmp_path: Path) -> Iterator[tuple[TestClient, str]]:
    game = tmp_path / "game"
    game.mkdir()
    with TestClient(create_app(tmp_path / "state")) as client:
        state = client.app.state.udify
        job = state.runner.create_job(str(game), "test")
        state.store.append_event(job.job_id, "created", "extra_one")
        state.store.append_event(job.job_id, "created", "extra_two")
        state.store.transition(job, JobStatus.FAILED, event="failed")
        yield client, job.job_id


@pytest.mark.parametrize(
    ("header", "query", "expected_after"),
    [
        (None, 1, 1),
        ("2", 1, 2),
        ("1", 3, 1),
        ("0", 3, 0),
        ("abc", 2, 2),
        ("-1", 2, 2),
        ("1.5", 2, 2),
        ("", 2, 2),
    ],
)
def test_real_http_resume_matches_polling(
    completed_client: tuple[TestClient, str], header: str | None, query: int, expected_after: int
) -> None:
    client, job_id = completed_client
    headers = {} if header is None else {"Last-Event-ID": header}
    response = client.get(f"/api/v0/jobs/{job_id}/events?after_seq={query}", headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    frames = response.text.split("\n\n")
    actual = [
        json.loads(frame.split("data: ", 1)[1]) for frame in frames if "event: job\n" in frame
    ]
    expected = client.get(f"/api/v0/jobs/{job_id}?after_seq={expected_after}").json()["data"][
        "events"
    ]
    assert actual == expected
    assert all(f"id: {event['seq']}\n" in response.text for event in actual)
    assert "event: done" in response.text


def test_negative_query_rejected(completed_client: tuple[TestClient, str]) -> None:
    client, job_id = completed_client
    assert client.get(f"/api/v0/jobs/{job_id}/events?after_seq=-1").status_code == 422
