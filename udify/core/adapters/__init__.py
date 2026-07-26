"""引擎适配器层（v3）。

对应 ITERATION-PLAN-2026-07.md §4.2。把硬编码的引擎分支变成契约：
任何引擎通过实现 ``EngineAdapter`` 协议接入。
"""

from udify.core.adapters.base import DetectionResult, EngineAdapter, span_for_node
from udify.core.adapters.miu2d import Miu2dAdapter

__all__ = ["DetectionResult", "EngineAdapter", "Miu2dAdapter", "span_for_node"]
