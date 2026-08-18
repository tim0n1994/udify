"""评测体系 + ModStack 合并测试（iter3 N4 / S5-BENCH）。@bench marker。"""

import pytest

from tests.bench.cases import load_cases
from tests.bench.runner import (
    detect_merge_conflicts,
    heuristic_engine,
    resolver_engine,
    run_ab,
    run_engine,
)

pytestmark = pytest.mark.bench


def test_cases_count_at_least_30():
    cases = load_cases()
    assert len(cases) >= 30


def test_outsider_cases_present():
    assert len(load_cases(domain="outsider")) >= 10


def test_ab_runs_offline_no_network():
    """A/B 评测离线跑通，不触网。"""
    report = run_ab()
    assert set(report.keys()) == {"heuristic", "resolver", "mock_llm"}
    for _name, r in report.items():
        assert 0.0 <= r["intent_type_accuracy"] <= 1.0
        assert r["total"] >= 30


def test_resolver_avoids_misfire_better_than_heuristic():
    """target_resolver 的误伤规避应优于（或等于）启发式。"""
    h = run_engine(heuristic_engine, "heuristic")
    r = run_engine(resolver_engine, "resolver")
    assert r.misfire_avoidance >= h.misfire_avoidance


def test_merge_conflict_detected_same_property():
    base = {"hp": 100, "atk": 10}
    a = {"hp": 200}
    b = {"hp": 300}
    conflicts = detect_merge_conflicts(base, a, b)
    assert len(conflicts) == 1
    assert "200" in conflicts[0].detail and "300" in conflicts[0].detail


def test_merge_no_conflict_when_same_value():
    base = {"hp": 100}
    a = {"hp": 200}
    b = {"hp": 200}
    assert detect_merge_conflicts(base, a, b) == []


def test_merge_no_conflict_disjoint_keys():
    base = {"hp": 100, "atk": 10}
    a = {"hp": 200}
    b = {"atk": 20}
    assert detect_merge_conflicts(base, a, b) == []
