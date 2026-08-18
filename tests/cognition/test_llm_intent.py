"""LLM 意图路径测试（iter3 N1）。无 key 全降级，不触网。"""

from udify.core.cognition.intent import StructuredIntent
from udify.core.cognition.llm_intent import (
    JobLLMBudget,
    LLMIntentProposer,
    merge_intent,
)


def _baseline() -> StructuredIntent:
    si = StructuredIntent()
    si.primary_goal = {
        "type": "difficulty_adjustment",
        "target": "",
        "direction": "increase",
        "magnitude": "",
    }
    return si


def test_no_key_degrades_without_network(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = LLMIntentProposer()
    assert p.is_available() is False
    res = p.propose("把 Boss 血量翻倍", "graph summary", _baseline(), JobLLMBudget())
    assert res.degraded is True
    assert res.candidate is None
    assert res.budget.calls_made == 0, "must not make any call without key"


def test_budget_limits_calls(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = LLMIntentProposer()
    b = JobLLMBudget(max_calls=0)
    res = p.propose("x", "y", _baseline(), b)
    assert res.degraded is True


def test_merge_rule_first_llm_fills_gaps():
    base = _baseline()  # target empty
    cand = StructuredIntent()
    cand.primary_goal = {"type": "", "target": "boss_01", "direction": "", "magnitude": "extreme"}
    cand.negative_preferences = ["no_hp_inflation"]
    merged = merge_intent(base, cand)
    # 规则优先：type/direction 保留规则的
    assert merged.primary_goal["type"] == "difficulty_adjustment"
    assert merged.primary_goal["direction"] == "increase"
    # LLM 填空缺：target/magnitude
    assert merged.primary_goal["target"] == "boss_01"
    assert merged.primary_goal["magnitude"] == "extreme"
    assert merged.negative_preferences == ["no_hp_inflation"]


def test_merge_none_candidate_returns_baseline():
    base = _baseline()
    merged = merge_intent(base, None)
    assert merged is base or merged.primary_goal == base.primary_goal


def test_extract_candidate_handles_malformed():
    # 没有 tool_use block 时返回 None
    class FakeResp:
        content = []

    assert LLMIntentProposer._extract_candidate(FakeResp(), _baseline()) is None


def test_budget_token_tracking():
    b = JobLLMBudget(max_total_tokens=100)
    assert b.can_call()
    b.record(60, 10)
    assert b.can_call()
    b.record(20, 20)
    assert not b.can_call()  # 110 > 100
