"""
LLM 意图路径的可观测性与降级信封（iter4 M2，T2-LLM-OBS-COST 研究落地）。

每次意图解析产出一个 IntentDecisionTrace，记录：
- 决策路径（heuristic / llm_candidate / merged）
- token 用量与成本估算（不依赖 vendor 私有字段，无 key 时为零）
- 降级原因码（可被前端展示，可进 audit chain）

设计原则（T2 研究结论）：
- 纯数据，frozen，可序列化（to_dict / JSON），无网络副作用。
- 无 key 时全字段零/默认，不触网。
- 与 tool_gateway/audit.py 的链式哈希审计兼容（canonical_json 提供稳定哈希输入）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DecisionPath(StrEnum):
    """意图解析走过的路径。"""

    HEURISTIC = "heuristic"
    LLM_CANDIDATE = "llm_candidate"
    MERGED = "merged"


class DegradationReasonCode(StrEnum):
    """降级原因码（前端展示 + audit 可追溯）。"""

    NO_KEY = "NO_KEY"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMIT = "RATE_LIMIT"


# 主因挑选优先级（M5-PR1）：多个降级原因同时成立时，显示层按此序挑第一个。
# 排序依据是「哪个最先阻断调用、且最可操作」——预算为 0 时无论凭证如何都不会发起
# 调用，故 BUDGET_EXHAUSTED 优先于 NO_KEY。集合里其余原因不丢失，只是不作主因。
_REASON_PRIORITY: tuple[DegradationReasonCode, ...] = (
    DegradationReasonCode.BUDGET_EXHAUSTED,
    DegradationReasonCode.NO_KEY,
    DegradationReasonCode.RATE_LIMIT,
    DegradationReasonCode.TIMEOUT,
    DegradationReasonCode.NETWORK_ERROR,
    DegradationReasonCode.VALIDATION_FAILED,
    DegradationReasonCode.MALFORMED_RESPONSE,
)

# 每个 reason 的可解释描述：是否可重试 + 建议动作（前端/CLI 展示）。
_REASON_TABLE: dict[DegradationReasonCode, tuple[bool, str]] = {
    DegradationReasonCode.NO_KEY: (False, "未设置 ANTHROPIC_API_KEY，走启发式降级（正常）。"),
    DegradationReasonCode.BUDGET_EXHAUSTED: (False, "LLM 预算耗尽，降级启发式。"),
    DegradationReasonCode.TIMEOUT: (True, "LLM 调用超时，可重试或降级。"),
    DegradationReasonCode.VALIDATION_FAILED: (True, "LLM 输出校验失败，可重试或降级。"),
    DegradationReasonCode.MALFORMED_RESPONSE: (True, "LLM 响应格式错误，可重试或降级。"),
    DegradationReasonCode.NETWORK_ERROR: (True, "网络错误，可重试或降级。"),
    DegradationReasonCode.RATE_LIMIT: (True, "速率限制，稍后可重试或降级。"),
}


def reason_descriptor(code: DegradationReasonCode) -> tuple[bool, str]:
    """返回 (retryable, suggested_action)。"""
    return _REASON_TABLE.get(code, (False, "未知降级原因。"))


def utc_now() -> datetime:
    return datetime.now(UTC)


def canonical_json(value: Mapping[str, Any]) -> str:
    """稳定 JSON 序列化（键排序），用于 audit chain 哈希输入。"""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class TokenUsageTrace:
    """单次或累计 LLM 调用的 token 用量。无 key 时全零。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def add(self, other: TokenUsageTrace) -> TokenUsageTrace:
        return TokenUsageTrace(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens + other.cache_read_input_tokens,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class CostTrace:
    """LLM 调用成本估算（美元，字符串存 Decimal 避免浮点漂移）。"""

    input_cost_usd: str = "0"
    output_cost_usd: str = "0"
    total_cost_usd: str = "0"

    def to_dict(self) -> dict[str, str]:
        return {
            "input_cost_usd": self.input_cost_usd,
            "output_cost_usd": self.output_cost_usd,
            "total_cost_usd": self.total_cost_usd,
        }


@dataclass(frozen=True, slots=True)
class IntentDecisionTrace:
    """意图解析的完整决策记录。

    可序列化进 sqlite job_events 表与 audit chain（canonical_json 提供稳定哈希）。
    前端可读取 decision_path / confidence / degradation_reason 展示决策路径。
    """

    decision_path: DecisionPath
    confidence: float
    degradation_reason: DegradationReasonCode | None = None
    degradation_reasons: tuple[DegradationReasonCode, ...] = ()
    usage: TokenUsageTrace = field(default_factory=TokenUsageTrace)
    cost: CostTrace = field(default_factory=CostTrace)
    model: str | None = None
    latency_ms: int = 0
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())

    def __post_init__(self) -> None:
        """让单值主因与原因集合互相自洽（M5-PR1 降级原因正交化）。

        单值 ``degradation_reason`` 会让先判定者掩盖后判定者——真实缺陷是「无 Key
        且预算耗尽」时预算耗尽在生产中永不可见。改为集合后所有成立的原因都留痕，
        主因只是**显示层**按优先级挑出来的那个，不再吞掉其余事实。

        两个方向都补齐，保持既有构造点全部向后兼容：
        - 只给集合 → 主因 = 集合中优先级最高者
        - 只给主因 → 集合 = (主因,)
        """
        if self.degradation_reasons and self.degradation_reason is None:
            primary = min(
                self.degradation_reasons,
                key=lambda r: (
                    _REASON_PRIORITY.index(r) if r in _REASON_PRIORITY else len(_REASON_PRIORITY)
                ),
            )
            object.__setattr__(self, "degradation_reason", primary)
        elif self.degradation_reason is not None and not self.degradation_reasons:
            object.__setattr__(self, "degradation_reasons", (self.degradation_reason,))

    @property
    def degraded(self) -> bool:
        return self.degradation_reason is not None

    @property
    def retryable(self) -> bool:
        if self.degradation_reason is None:
            return False
        return reason_descriptor(self.degradation_reason)[0]

    @property
    def suggested_action(self) -> str:
        if self.degradation_reason is None:
            return ""
        return reason_descriptor(self.degradation_reason)[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_path": self.decision_path.value,
            "confidence": self.confidence,
            "degradation_reason": self.degradation_reason.value
            if self.degradation_reason
            else None,
            # 全部成立的原因，供运维排查；主因只是显示层的挑选结果
            "degradation_reasons": [r.value for r in self.degradation_reasons],
            "degraded": self.degraded,
            "retryable": self.retryable,
            "suggested_action": self.suggested_action,
            "usage": self.usage.to_dict(),
            "cost": self.cost.to_dict(),
            "model": self.model,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }

    def canonical(self) -> str:
        """稳定序列化，用于 audit chain 哈希。"""
        return canonical_json(self.to_dict())


def heuristic_trace(confidence: float = 0.6) -> IntentDecisionTrace:
    """启发式路径的 trace（无 LLM 调用）。"""
    return IntentDecisionTrace(
        decision_path=DecisionPath.HEURISTIC,
        confidence=confidence,
        degradation_reason=None,
    )


def degraded_trace(reason: DegradationReasonCode, confidence: float = 0.4) -> IntentDecisionTrace:
    """降级到启发式的 trace（带原因码）。"""
    return IntentDecisionTrace(
        decision_path=DecisionPath.HEURISTIC,
        confidence=confidence,
        degradation_reason=reason,
    )
