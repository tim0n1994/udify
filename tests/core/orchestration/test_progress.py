"""iter4 M4 — 流式进度与取消测试。"""

from __future__ import annotations

import os
import tempfile

from udify.core.orchestration.progress import (
    CancellationToken,
    ProgressEmitter,
    ProgressStage,
    ProgressStore,
)


def test_progress_event_to_dict():
    from udify.core.orchestration.progress import ProgressEvent

    # pct is an explicit field; the emitter computes it on emit.
    evt = ProgressEvent(
        job_id="j1", stage=ProgressStage.PERCEIVING, pct=50.0, current=5, total=10, seq=1
    )
    d = evt.to_dict()
    assert d["stage"] == "perceiving"
    assert d["pct"] == 50.0
    assert d["seq"] == 1


def test_emitter_emits_and_broadcasts():
    em = ProgressEmitter("j1")
    received = []
    em.subscribe(received.append)
    evt = em.emit(ProgressStage.PERCEIVING, "scanning", current=3, total=10)
    assert evt.seq == 1
    assert evt.pct == 30.0
    assert len(received) == 1
    assert received[0].stage == ProgressStage.PERCEIVING
    assert em.last.seq == 1


def test_emitter_seq_increments():
    em = ProgressEmitter("j1")
    e1 = em.emit(ProgressStage.PERCEIVING)
    e2 = em.emit(ProgressStage.PERCEIVING)
    e3 = em.emit(ProgressStage.PLANNING)
    assert (e1.seq, e2.seq, e3.seq) == (1, 2, 3)


def test_emitter_subscriber_error_does_not_crash():
    em = ProgressEmitter("j1")

    def bad(_):
        raise RuntimeError("boom")

    em.subscribe(bad)
    em.subscribe(lambda e: None)
    evt = em.emit(ProgressStage.PLANNING)  # bad 订阅者不崩溃
    assert evt.seq == 1


def test_cancellation_token():
    tok = CancellationToken()
    assert not tok.is_cancelled()
    tok.cancel()
    assert tok.is_cancelled()
    tok.clear()
    assert not tok.is_cancelled()


def test_progress_store_persistence_and_recovery():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = ProgressStore(path)
        em = ProgressEmitter("job-x")
        em.subscribe(store.append)
        em.emit(ProgressStage.PERCEIVING, "a", current=1, total=5)
        em.emit(ProgressStage.PERCEIVING, "b", current=3, total=5)
        em.emit(ProgressStage.PLANNING, "c", current=2, total=10)
        # 查历史
        hist = store.history("job-x")
        assert len(hist) == 3
        assert hist[0].detail == "a"
        assert hist[-1].stage == ProgressStage.PLANNING
        # 增量查询
        after1 = store.history("job-x", after_seq=1)
        assert len(after1) == 2
        # latest
        latest = store.latest("job-x")
        assert latest is not None
        assert latest.stage == ProgressStage.PLANNING
        store.close()
        # 重新打开（模拟崩溃恢复）
        store2 = ProgressStore(path)
        hist2 = store2.history("job-x")
        assert len(hist2) == 3, "进度在重开后恢复"
        store2.close()
    finally:
        os.unlink(path)


def test_progress_store_isolation_between_jobs():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        store = ProgressStore(path)
        store.append(_mk("job-a", 1, ProgressStage.PERCEIVING))
        store.append(_mk("job-b", 1, ProgressStage.PLANNING))
        assert len(store.history("job-a")) == 1
        assert len(store.history("job-b")) == 1
        assert store.history("job-a")[0].stage == ProgressStage.PERCEIVING
        store.close()
    finally:
        os.unlink(path)


def _mk(job_id, seq, stage):
    from udify.core.orchestration.progress import ProgressEvent

    return ProgressEvent(job_id=job_id, seq=seq, stage=stage)
