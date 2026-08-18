"""
LLM 成本估算（iter4 M2，T2-LLM-OBS-COST 研究落地）。

按真实模型定价估算 LLM 调用成本（USD），不依赖 vendor SDK 私有字段。
定价来源：Anthropic 公开定价页（https://www.anthropic.com/pricing），
采集日期标注于 PRICING_TABLE 的 _SOURCE_DATE。定价随时间变动，需定期更新。

设计原则：
- 纯函数，无网络。
- Decimal 精度，字符串输出避免浮点漂移。
- 未知模型返回零成本（fail-safe，不 crash）。
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from udify.core.cognition.intent_trace import CostTrace, TokenUsageTrace

# 定价单位：美元 / 百万 token。来源 Anthropic 公开定价页。
_SOURCE_DATE = "2026-08-06"

# (input_per_mtok, output_per_mtok, cache_write_per_mtok, cache_read_per_mtok)
# None 表示该模型不支持该计费维度（按零计）。
PRICING_TABLE: Mapping[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    "claude-3-5-sonnet-20241022": (
        Decimal("3.00"),
        Decimal("15.00"),
        Decimal("3.75"),
        Decimal("0.30"),
    ),
    "claude-3-5-haiku-20241022": (
        Decimal("0.80"),
        Decimal("4.00"),
        Decimal("1.00"),
        Decimal("0.08"),
    ),
    "claude-sonnet-4-20250514": (
        Decimal("3.00"),
        Decimal("15.00"),
        Decimal("3.75"),
        Decimal("0.30"),
    ),
    # 默认回退（未知模型）：零成本，fail-safe。
}


def _per_mtok_to_per_token(per_mtok: Decimal) -> Decimal:
    return per_mtok / Decimal("1000000")


def estimate_cost(usage: TokenUsageTrace, model: str) -> CostTrace:
    """估算单次调用的成本。

    Args:
        usage: token 用量。
        model: 模型名（须匹配 PRICING_TABLE key）。

    Returns:
        CostTrace（字符串存 Decimal）。未知模型返回全零。
    """
    rates = PRICING_TABLE.get(model)
    if rates is None:
        return CostTrace()
    in_rate, out_rate, cw_rate, cr_rate = rates
    input_cost = _per_mtok_to_per_token(in_rate) * Decimal(usage.input_tokens)
    output_cost = _per_mtok_to_per_token(out_rate) * Decimal(usage.output_tokens)
    cache_write_cost = _per_mtok_to_per_token(cw_rate) * Decimal(usage.cache_creation_input_tokens)
    cache_read_cost = _per_mtok_to_per_token(cr_rate) * Decimal(usage.cache_read_input_tokens)
    total = input_cost + output_cost + cache_write_cost + cache_read_cost

    def fmt(d: Decimal) -> str:
        return str(d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))

    return CostTrace(
        input_cost_usd=fmt(input_cost),
        output_cost_usd=fmt(output_cost + cache_write_cost + cache_read_cost),
        total_cost_usd=fmt(total),
    )


def pricing_source_date() -> str:
    """返回定价采集日期（审计可追溯）。"""
    return _SOURCE_DATE
