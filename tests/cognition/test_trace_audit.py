"""iter4 M2 PR3 — IntentDecisionTrace → audit chain + job_events 收敛测试（T2-LLM-OBS-COST）。

PRD AC#4：IntentDecisionTrace 可序列化进 sqlite job_events + audit chain（链式哈希不断）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from udify.core.cognition.intent_trace import (
    DecisionPath,
    DegradationReasonCode,
    IntentDecisionTrace,
    TokenUsageTrace,
)
from udify.core.cognition.llm_pricing import estimate_cost
from udify.core.cognition.trace_audit import (
    record_trace_event,
    trace_to_event_payload,
    verify_trace_chain,
)
from udify.core.orchestration import JobStore
from udify.core.orchestration.mod_job import ModJob


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.db")


def _make_job(store: JobStore, job_id: str = "job-trace-1") -> str:
    import dataclasses

    base = ModJob.new(game_root="/tmp/game", intent="测试", artifacts_dir="/tmp/art")
    job = dataclasses.replace(base, job_id=job_id)
    store.save(job)
    return job_id


def _make_trace(degraded: bool = False) -> IntentDecisionTrace:
    usage = TokenUsageTrace(input_tokens=100, output_tokens=50)
    cost = estimate_cost(usage, "claude-3-5-sonnet")
    return IntentDecisionTrace(
        decision_path=DecisionPath.HEURISTIC if degraded else DecisionPath.MERGED,
        confidence=0.85,
        degradation_reason=DegradationReasonCode.NO_KEY if degraded else None,
        usage=usage,
        cost=cost,
        model="claude-3-5-sonnet",
        latency_ms=250,
    )


class TestTraceToEventPayload:
    def test_payload_is_flat_and_serializable(self):
        trace = _make_trace()
        payload = trace_to_event_payload(trace)
        assert "decision_path" in payload
        assert "confidence" in payload
        assert "cost" in payload
        assert "canonical" in payload
        # 可 JSON 序列化
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "decision_path" in serialized

    def test_payload_includes_degradation_info(self):
        trace = _make_trace(degraded=True)
        payload = trace_to_event_payload(trace)
        assert payload["degraded"] is True
        assert payload["degradation_reason"] == "NO_KEY"
        assert payload["retryable"] is False  # NO_KEY 不可重试（需用户设 key）


class TestRecordTraceEvent:
    def test_records_trace_into_job_events(self, store):
        job_id = _make_job(store)
        trace = _make_trace()
        record_hash = record_trace_event(store, job_id, trace)
        assert record_hash  # 非空哈希

        events = store.events(job_id)
        assert len(events) == 1
        assert events[0].event == "llm_intent_trace"

    def test_degraded_trace_uses_degraded_event_name(self, store):
        job_id = _make_job(store)
        trace = _make_trace(degraded=True)
        record_trace_event(store, job_id, trace)
        events = store.events(job_id)
        assert "degraded:" in events[0].event

    def test_chain_hash_not_broken_after_multiple_traces(self, store):
        """PRD AC#4：多条 trace 事件后链式哈希不断。"""
        job_id = _make_job(store)
        for _ in range(3):
            record_trace_event(store, job_id, _make_trace())
        assert verify_trace_chain(store, job_id) is True

    def test_payload_preserved_in_event(self, store):
        job_id = _make_job(store)
        trace = _make_trace()
        record_trace_event(store, job_id, trace)
        events = store.events(job_id)
        payload = events[0].payload
        assert payload["decision_path"] == "merged"
        assert payload["usage"]["input_tokens"] == 100


class TestVerifyTraceChain:
    def test_empty_events_returns_true(self, store):
        job_id = _make_job(store)
        assert verify_trace_chain(store, job_id) is True

    def test_chain_intact_after_single_trace(self, store):
        """单条 trace 事件后链式哈希完整。"""
        job_id = _make_job(store)
        record_trace_event(store, job_id, _make_trace())
        assert verify_trace_chain(store, job_id) is True
