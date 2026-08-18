"""
IntentDecisionTrace → audit chain + job_events 收敛（iter4 M2 PR3，T2-LLM-OBS-COST）。

把意图决策 trace 序列化进 JobStore 的事件流（链式哈希不断），
并提供链完整性验证。这是 M2 PRD AC#4 的实现：
「IntentDecisionTrace 可序列化进 sqlite job_events + audit chain（链式哈希不断）」。

设计原则（T2 研究结论）：
- trace 是纯数据，序列化稳定（canonical_json），审计链不断。
- 降级原因进 payload，前端可渲染。
- 纯函数式适配器，不修改 trace 本身。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from udify.core.cognition.intent_trace import IntentDecisionTrace

if TYPE_CHECKING:
    from udify.core.orchestration import JobStore


def trace_to_event_payload(trace: IntentDecisionTrace) -> dict[str, Any]:
    """把 IntentDecisionTrace 转成 JobEvent payload（稳定序列化）。

    payload 结构扁平，前端可直接消费 decision_path / degraded / cost 等。
    """
    d = trace.to_dict()
    return {
        "decision_path": d["decision_path"],
        "confidence": d["confidence"],
        "degraded": d["degraded"],
        "degradation_reason": d["degradation_reason"],
        "retryable": d["retryable"],
        "suggested_action": d["suggested_action"],
        "usage": d["usage"],
        "cost": d["cost"],
        "model": d["model"],
        "latency_ms": d["latency_ms"],
        "canonical": trace.canonical(),  # 用于审计链哈希验证
    }


def record_trace_event(
    store: JobStore,
    job_id: str,
    trace: IntentDecisionTrace,
    stage: str = "planning",
) -> str:
    """把 trace 追加到 JobStore 事件流（链式哈希）。

    Args:
        store: JobStore 实例。
        job_id: 任务 id。
        trace: 意图决策 trace。
        stage: 事件阶段标签（默认 planning）。

    Returns:
        追加的 record_hash（链式哈希凭证）。
    """
    payload = trace_to_event_payload(trace)
    event_name = "llm_intent_trace"
    if trace.degraded:
        reason = trace.degradation_reason.value if trace.degradation_reason else "unknown"
        event_name = f"llm_intent_degraded:{reason}"
    job_event = store.append_event(job_id, stage, event_name, payload)
    return job_event.record_hash


def verify_trace_chain(store: JobStore, job_id: str) -> bool:
    """验证某 job 的所有 trace 事件链式哈希不断。

    JobStore.append_event 内部已做链式哈希；此函数重新验证 events 的
    prev_hash → record_hash 链。
    """
    events = store.events(job_id)
    if not events:
        return True
    prev_hash = events[0].prev_hash
    for evt in events:
        if evt.prev_hash != prev_hash:
            return False
        prev_hash = evt.record_hash
    return True
