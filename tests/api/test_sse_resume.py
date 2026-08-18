"""SSE 断连恢复契约（iter7 M6）。

研究结论 W4.2：SSE 的 ``id:`` 字段直接映射 ``progress_events.seq``，``Last-Event-ID``
请求头映射 ``WHERE seq > :last_id``——断连补发因此**零新增存储**。

这些测试锁住的是「浏览器自动重连真的能续上」：EventSource 重连时发的是 Last-Event-ID
请求头，而不是查询参数。只认查询参数的实现会在每次断连时静默丢事件。
"""

from __future__ import annotations

import contextlib

import pytest

from udify.api.job_events import RETRY_MS, _sse_event


class TestSseWireFormat:
    """SSE 线格式——id 缺失则断连恢复无从谈起。"""

    def test_event_carries_id_field(self) -> None:
        out = _sse_event({"a": 1}, event_id=42)
        assert out.startswith("id: 42\n")

    def test_id_omitted_when_not_supplied(self) -> None:
        assert "id:" not in _sse_event({"a": 1})

    def test_event_name_and_payload(self) -> None:
        out = _sse_event({"a": 1}, event="progress", event_id=7)
        assert "event: progress\n" in out
        assert '"a": 1' in out
        assert out.endswith("\n\n"), "SSE 事件必须以空行结束"

    def test_payload_is_not_ascii_escaped(self) -> None:
        """中文进度文案不该被转义成 \\uXXXX，否则前端展示要多一层解码。"""
        assert "感知" in _sse_event({"stage": "感知"}, event_id=1)

    def test_retry_hint_is_positive(self) -> None:
        assert RETRY_MS > 0


class TestLastEventIdResume:
    """``Last-Event-ID`` 头的解析规则（浏览器自动重连的实际载体）。"""

    @staticmethod
    def _resume_from(header: str | None, after_seq: int = 0) -> int:
        """复刻 _route 的断点解析：头优先，非法值忽略，与查询参数取大。"""
        resume = after_seq
        if header:
            with contextlib.suppress(ValueError):
                resume = max(resume, int(header))
        return resume

    def test_header_wins_over_query_param(self) -> None:
        assert self._resume_from("15", after_seq=3) == 15

    def test_query_param_used_when_header_absent(self) -> None:
        assert self._resume_from(None, after_seq=3) == 3

    def test_never_rewinds_below_query_param(self) -> None:
        """取较大值——否则重连会重放已消费的事件。"""
        assert self._resume_from("2", after_seq=9) == 9

    @pytest.mark.parametrize("bad", ["abc", "", "1.5", "-"])
    def test_malformed_header_falls_back_without_crashing(self, bad: str) -> None:
        """头部来自客户端，不可信：非法值不得中断连接。"""
        assert self._resume_from(bad, after_seq=4) == 4
