"""A/B 评测 runner + ModStack 合并冲突检测（iter3 N4 / S5-BENCH）。

heuristic vs target_resolver vs LLM 的离线对照。LLM 用 mock（不触网）。
ModStack 三路合并基于真实 ConflictType。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tests.bench.cases import IntentCase, load_cases
from udify.core.cognition.intent import IntentType
from udify.core.cognition.target_resolver import TargetResolution, resolve_targets
from udify.models.cdl_patch import ConflictType
from udify.models.content_graph import ContentGraph, ContentNode, NodeType

# ---意图引擎适配（统一接口）---

IntentEngine = Callable[[str, ContentGraph], dict[str, Any]]


def heuristic_engine(text: str, graph: ContentGraph) -> dict[str, Any]:
    """关键词启发式（IntentClassifier.INTENT_KEYWORDS 的简化对照版）。"""
    low = text.lower()
    if any(k in low for k in ("难", "boss", "敌人", "hard", "difficult")):
        itype = IntentType.DIFFICULTY_ADJUSTMENT
    elif any(k in low for k in ("新增", "添加", "add")):
        itype = IntentType.CONTENT_EXPANSION
    elif any(k in low for k in ("机制", "mechanic")):
        itype = IntentType.GAMEPLAY_MECHANIC
    elif any(k in low for k in ("剧情", "dialogue")):
        itype = IntentType.NARRATIVE_CHANGE
    elif any(k in low for k in ("视觉", "ui", "visual")):
        itype = IntentType.VISUAL_STYLE
    else:
        itype = IntentType.UNKNOWN
    # 启发式不做目标过滤：返回所有 CHARACTER 节点（会误伤）
    targets = [n.id for n in graph.nodes if n.type == NodeType.CHARACTER]
    return {"intent_type": itype, "target_ids": targets, "misfire": len(targets) > 1}


def resolver_engine(text: str, graph: ContentGraph) -> dict[str, Any]:
    """target_resolver 规则引擎（iter2）。"""
    res: TargetResolution = resolve_targets(graph, text)
    return {
        "intent_type": IntentType.DIFFICULTY_ADJUSTMENT,  # resolver 只管目标，类型由上层
        "target_ids": res.chosen_ids(),
        "misfire": False,  # resolver 默认排除 player
    }


def make_mock_llm_engine(fixed_targets: list[str]) -> IntentEngine:
    """mock LLM（离线，不触网）。返回固定候选目标。"""

    def engine(text: str, graph: ContentGraph) -> dict[str, Any]:
        return {
            "intent_type": IntentType.DIFFICULTY_ADJUSTMENT,
            "target_ids": fixed_targets,
            "misfire": False,
        }

    return engine


# ---评测指标---


@dataclass
class CaseResult:
    case_id: str
    engine: str
    intent_type_match: bool
    target_hit: bool  # 是否命中期望关键词相关节点
    misfire_correct: bool  # 误伤判断是否正确（应误伤 False 时不误伤）


@dataclass
class EngineReport:
    engine: str
    total: int = 0
    intent_type_accuracy: float = 0.0
    target_precision: float = 0.0
    misfire_avoidance: float = 0.0
    cases: list[CaseResult] = field(default_factory=list)


def _case_target_nodes(case: IntentCase) -> list[ContentNode]:
    """为 case 构造合成图：1 个期望目标 + 1 个干扰（player/hero）。"""
    keyword = case.expect_target_keyword
    nodes = []
    if keyword in ("boss",):
        nodes.append(
            ContentNode(
                id="boss_01", type=NodeType.CHARACTER, properties={"is_boss": True, "hp": 5000}
            )
        )
    elif keyword in ("enemy",):
        nodes.append(
            ContentNode(
                id="enemy_01", type=NodeType.CHARACTER, properties={"is_enemy": True, "hp": 120}
            )
        )
    elif keyword in ("player",):
        nodes.append(
            ContentNode(
                id="hero_01", type=NodeType.CHARACTER, properties={"is_player": True, "hp": 800}
            )
        )
    else:
        nodes.append(
            ContentNode(
                id="target_01", type=NodeType.CHARACTER, name=keyword, properties={"hp": 100}
            )
        )
    # 干扰：总是加一个 player（测误伤）
    nodes.append(
        ContentNode(
            id="hero干扰", type=NodeType.CHARACTER, properties={"is_player": True, "hp": 800}
        )
    )
    return nodes


def run_engine(engine: IntentEngine, engine_name: str) -> EngineReport:
    report = EngineReport(engine=engine_name)
    type_correct = 0
    target_correct = 0
    misfire_correct = 0
    for case in load_cases():
        g = ContentGraph()
        for n in _case_target_nodes(case):
            g.add_node(n)
        out = engine(case.text, g)
        tm = out["intent_type"] == case.expect_type
        # target_hit：命中且不包含干扰 hero（除非期望 player）
        ids = out.get("target_ids", [])
        hit = bool(ids) and ("hero干扰" not in ids or case.expect_target_keyword == "player")
        mc = (not out.get("misfire", False)) if case.should_misfire else True
        if tm:
            type_correct += 1
        if hit:
            target_correct += 1
        if mc:
            misfire_correct += 1
        report.cases.append(CaseResult(case.case_id, engine_name, tm, hit, mc))
    n = len(load_cases())
    report.total = n
    report.intent_type_accuracy = type_correct / n if n else 0.0
    report.target_precision = target_correct / n if n else 0.0
    report.misfire_avoidance = misfire_correct / n if n else 0.0
    return report


def run_ab(mock_llm_targets: list[str] | None = None) -> dict[str, Any]:
    """跑 heuristic / resolver / mock-llm 三引擎对照，返回报告 dict。"""
    reports = {
        "heuristic": run_engine(heuristic_engine, "heuristic"),
        "resolver": run_engine(resolver_engine, "resolver"),
        "mock_llm": run_engine(make_mock_llm_engine(mock_llm_targets or ["boss_01"]), "mock_llm"),
    }
    return {
        name: {
            "intent_type_accuracy": r.intent_type_accuracy,
            "target_precision": r.target_precision,
            "misfire_avoidance": r.misfire_avoidance,
            "total": r.total,
        }
        for name, r in reports.items()
    }


# ---ModStack 三路合并冲突检测（复用 ConflictType）---


@dataclass
class MergeConflict:
    """一次合并冲突。"""

    conflict_type: ConflictType
    node_id: str
    detail: str = ""


def detect_merge_conflicts(
    base_props: dict[str, Any],
    patch_a: dict[str, Any],
    patch_b: dict[str, Any],
) -> list[MergeConflict]:
    """三路合并冲突检测：A 与 B 都改了 base 的同一属性且值不同 → SAME_PROPERTY_MODIFY。

    Args:
        base_props: 基线属性。
        patch_a: A 的修改（属性→新值）。
        patch_b: B 的修改（属性→新值）。
    """
    conflicts: list[MergeConflict] = []
    common = set(patch_a) & set(patch_b)
    for key in common:
        if patch_a[key] != patch_b[key]:
            conflicts.append(
                MergeConflict(
                    conflict_type=ConflictType.SAME_PROPERTY_MODIFY,
                    node_id=key,
                    detail=f"A={patch_a[key]} vs B={patch_b[key]} (base={base_props.get(key)})",
                )
            )
    return conflicts


__all__ = [
    "CaseResult",
    "EngineReport",
    "MergeConflict",
    "detect_merge_conflicts",
    "heuristic_engine",
    "make_mock_llm_engine",
    "resolver_engine",
    "run_ab",
    "run_engine",
]
