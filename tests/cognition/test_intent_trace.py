"""iter4 M2 — IntentDecisionTrace / 降级信封 / token 成本计量 测试。"""

from __future__ import annotations

import json

from udify.core.cognition.intent_trace import (
    DecisionPath,
    DegradationReasonCode,
    IntentDecisionTrace,
    TokenUsageTrace,
    degraded_trace,
    heuristic_trace,
    reason_descriptor,
)
from udify.core.cognition.llm_budget import (
    BudgetDecision,
    BudgetLimit,
    LLMBudgetPolicy,
    ReservationRequest,
)
from udify.core.cognition.llm_pricing import (
    PRICING_TABLE,
    estimate_cost,
    pricing_source_date,
)

# --- intent_trace 纯数据 ---


def test_token_usage_total_and_add():
    a = TokenUsageTrace(input_tokens=100, output_tokens=50)
    b = TokenUsageTrace(input_tokens=200, cache_read_input_tokens=10)
    assert a.total_tokens == 150
    c = a.add(b)
    assert c.input_tokens == 300
    assert c.cache_read_input_tokens == 10
    assert c.total_tokens == 360


def test_heuristic_trace_not_degraded():
    t = heuristic_trace(0.7)
    assert t.decision_path == DecisionPath.HEURISTIC
    assert t.confidence == 0.7
    assert not t.degraded
    assert t.degradation_reason is None
    assert t.retryable is False


def test_degraded_trace_carries_reason():
    t = degraded_trace(DegradationReasonCode.NO_KEY)
    assert t.degraded
    assert t.degradation_reason == DegradationReasonCode.NO_KEY
    assert t.retryable is False  # NO_KEY not retryable
    assert "ANTHROPIC_API_KEY" in t.suggested_action


def test_reason_descriptor_retryable_table():
    assert reason_descriptor(DegradationReasonCode.TIMEOUT)[0] is True
    assert reason_descriptor(DegradationReasonCode.BUDGET_EXHAUSTED)[0] is False
    assert reason_descriptor(DegradationReasonCode.RATE_LIMIT)[0] is True


def test_trace_to_dict_serializable():
    t = IntentDecisionTrace(
        decision_path=DecisionPath.LLM_CANDIDATE,
        confidence=0.85,
        usage=TokenUsageTrace(input_tokens=500, output_tokens=200),
    )
    d = t.to_dict()
    # round-trip JSON
    s = json.dumps(d)
    d2 = json.loads(s)
    assert d2["decision_path"] == "llm_candidate"
    assert d2["usage"]["total_tokens"] == 700
    assert d2["degraded"] is False


def test_canonical_json_stable_for_audit():
    t = IntentDecisionTrace(decision_path=DecisionPath.MERGED, confidence=0.9)
    c1 = t.canonical()
    c2 = t.canonical()
    assert c1 == c2  # deterministic for audit hashing


def test_default_usage_is_zero_no_key_safe():
    t = heuristic_trace()
    assert t.usage.total_tokens == 0
    assert t.cost.total_cost_usd == "0"


# --- llm_pricing ---


def test_estimate_cost_known_model():
    usage = TokenUsageTrace(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = estimate_cost(usage, "claude-3-5-sonnet-20241022")
    # 3.00/M input + 15.00/M output = 18.00
    assert cost.total_cost_usd == "18.000000"


def test_estimate_cost_unknown_model_zero():
    usage = TokenUsageTrace(input_tokens=999_999, output_tokens=999_999)
    cost = estimate_cost(usage, "nonexistent-model")
    assert cost.total_cost_usd == "0"


def test_pricing_source_date_present():
    assert pricing_source_date() == "2026-08-06"


def test_pricing_table_has_keys():
    assert "claude-3-5-sonnet-20241022" in PRICING_TABLE


# --- llm_budget 三级护栏 ---


def test_budget_allows_within_limits():
    policy = LLMBudgetPolicy()
    req = ReservationRequest(job_id="job-1", estimated_tokens=1000)
    res = policy.reserve(req)
    assert res.allowed
    assert res.decision == BudgetDecision.ALLOWED
    assert res.reservation_id.startswith("job-1-")


def test_budget_denies_job_limit():
    policy = LLMBudgetPolicy(job_limit=BudgetLimit(max_tokens=100, max_calls=1))
    req = ReservationRequest(job_id="job-x", estimated_tokens=50)
    r1 = policy.reserve(req)
    assert r1.allowed
    from udify.core.cognition.intent_trace import TokenUsageTrace

    policy.settle(r1.reservation_id, TokenUsageTrace(input_tokens=50))
    # 第二次同 job 超过 max_calls=1
    r2 = policy.reserve(ReservationRequest(job_id="job-x", estimated_tokens=10))
    assert not r2.allowed
    assert r2.decision == BudgetDecision.DENIED_JOB


def test_budget_denies_global_limit():
    policy = LLMBudgetPolicy(
        global_limit=BudgetLimit(max_tokens=200, max_calls=10),
        job_limit=BudgetLimit(max_tokens=200, max_calls=10),
        daily_limit=BudgetLimit(max_tokens=200, max_calls=10),
    )
    r1 = policy.reserve(ReservationRequest(job_id="a", estimated_tokens=150))
    assert r1.allowed
    from udify.core.cognition.intent_trace import TokenUsageTrace

    policy.settle(r1.reservation_id, TokenUsageTrace(input_tokens=150))
    # 全局已用 150，再 100 超 200
    r2 = policy.reserve(ReservationRequest(job_id="b", estimated_tokens=100))
    assert not r2.allowed
    assert r2.decision == BudgetDecision.DENIED_GLOBAL


def test_budget_release_frees_pending():
    policy = LLMBudgetPolicy(job_limit=BudgetLimit(max_tokens=100, max_calls=1))
    r = policy.reserve(ReservationRequest(job_id="j", estimated_tokens=50))
    assert r.allowed
    policy.release(r.reservation_id)
    # 释放后可再次 reserve（pending 已清）
    r2 = policy.reserve(ReservationRequest(job_id="j", estimated_tokens=50))
    assert r2.allowed


def test_budget_concurrent_reserve_threadsafe():
    policy = LLMBudgetPolicy(
        global_limit=BudgetLimit(max_tokens=1000, max_calls=3),
        job_limit=BudgetLimit(max_tokens=1000, max_calls=1),
        daily_limit=BudgetLimit(max_tokens=1000, max_calls=3),
    )
    import threading

    results = []
    lock = threading.Lock()

    def try_reserve(job_id):
        r = policy.reserve(ReservationRequest(job_id=job_id, estimated_tokens=10))
        with lock:
            results.append(r.allowed)

    threads = [threading.Thread(target=try_reserve, args=(f"job-{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 三个不同 job，全局 max_calls=3，应全部允许
    assert all(results)
    assert len(results) == 3


# --- M2 PR2: IntentDecisionTrace 集成进 LLMIntentProposer ---


def test_proposer_no_key_emits_no_key_trace(monkeypatch):
    """无 key 时 propose() 返回 degraded + NO_KEY trace，不触网。"""
    from udify.core.cognition.intent import StructuredIntent
    from udify.core.cognition.llm_intent import JobLLMBudget, LLMIntentProposer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    proposer = LLMIntentProposer()
    assert not proposer.is_available()
    result = proposer.propose(
        "让 boss 更难",
        "graph summary",
        StructuredIntent(),
        JobLLMBudget(),
    )
    assert result.degraded
    assert result.trace is not None
    assert result.trace.degradation_reason is not None
    assert result.trace.degradation_reason.value == "NO_KEY"
    assert result.trace.decision_path.value == "heuristic"
    # 不触网：trace 的 usage 为零
    assert result.trace.usage.total_tokens == 0


def test_proposer_budget_exhausted_emits_budget_trace(monkeypatch):
    """预算耗尽时 propose() 返回 BUDGET_EXHAUSTED trace。"""
    from udify.core.cognition.intent import StructuredIntent
    from udify.core.cognition.llm_intent import JobLLMBudget, LLMIntentProposer

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-budget-test")
    proposer = LLMIntentProposer()
    # 预算已耗尽
    budget = JobLLMBudget(max_calls=0)
    result = proposer.propose("x", "y", StructuredIntent(), budget)
    assert result.degraded
    assert result.trace is not None
    assert result.trace.degradation_reason.value == "BUDGET_EXHAUSTED"


def test_proposer_trace_serializable_for_audit(monkeypatch):
    """trace 可序列化（进 audit chain 的前提）。"""
    import json as _json

    from udify.core.cognition.intent import StructuredIntent
    from udify.core.cognition.llm_intent import JobLLMBudget, LLMIntentProposer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    proposer = LLMIntentProposer()
    result = proposer.propose("x", "y", StructuredIntent(), JobLLMBudget())
    d = result.trace.to_dict()
    # round-trip
    s = _json.dumps(d)
    d2 = _json.loads(s)
    assert d2["degradation_reason"] == "NO_KEY"
    assert result.trace.canonical() == result.trace.canonical()  # stable
