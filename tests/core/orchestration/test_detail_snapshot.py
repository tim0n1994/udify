from __future__ import annotations

from pathlib import Path

import pytest

from udify.core.orchestration import JobStatus, JobStore
from udify.core.orchestration.mod_job import ModJob


def test_detail_keeps_one_snapshot_across_concurrent_wal_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "jobs.db"
    reader = JobStore(path)
    writer = JobStore(path)
    try:
        job = ModJob.new("/game", "intent", "/artifacts")
        reader.save(job)
        reader.append_event(job.job_id, job.status.value, "job_created")
        get_original = reader.get
        committed = False

        def get_then_commit(job_id: str) -> ModJob | None:
            nonlocal committed
            snapshot = get_original(job_id)
            if not committed:
                writer.transition(job, JobStatus.FAILED, event="concurrent_failure")
                committed = True
            return snapshot

        monkeypatch.setattr(reader, "get", get_then_commit)
        snapshot, events, valid = reader.read_detail(job.job_id)
        assert committed
        assert snapshot is not None and snapshot.status == JobStatus.CREATED
        assert [event.stage for event in events] == ["created"]
        assert valid
        next_snapshot, next_events, next_valid = reader.read_detail(job.job_id, events[-1].seq)
        assert next_snapshot is not None and next_snapshot.status == JobStatus.FAILED
        assert [event.stage for event in next_events] == ["failed"]
        assert next_valid
    finally:
        writer.close()
        reader.close()


def test_detail_audit_uses_same_snapshot_as_returned_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = JobStore(tmp_path / "jobs.db")
    writer = JobStore(tmp_path / "jobs.db")
    try:
        job = ModJob.new("/game", "intent", "/artifacts")
        reader.save(job)
        reader.append_event(job.job_id, job.status.value, "job_created")
        original_events = reader.events
        changed = False

        def events_then_tamper(job_id: str, after_seq: int = 0) -> list:
            nonlocal changed
            events = original_events(job_id, after_seq)
            if not changed:
                with writer._lock, writer._conn:
                    writer._conn.execute(
                        "UPDATE job_events SET event = 'tampered' WHERE job_id = ?", (job_id,)
                    )
                changed = True
            return events

        monkeypatch.setattr(reader, "events", events_then_tamper)
        _, events, valid = reader.read_detail(job.job_id)
        assert events[0].event == "job_created"
        assert valid
        assert not reader.verify_chain(job.job_id)
    finally:
        writer.close()
        reader.close()
