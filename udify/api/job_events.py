"""
SSE 进度事件流（iter4 M4 PR2，T4-STREAMING-UX 研究落地）。

``GET /api/v0/jobs/{job_id}/events`` 返回 Server-Sent Events 流：
- 连接建立时先重放已持久化的历史事件（after_seq 增量）。
- 之后每秒心跳（SSE comment ``: ping``），并在有新事件时推送。
- 任务进入终态（completed/failed/rejected/rolled_back）时推送最后一个事件后关闭。

设计原则（T4 研究结论）：
- 进度是「best-effort 观测」，SSE 不影响状态机正确性。
- 不依赖额外基础设施（no Redis/queue）——单用户本机场景直接轮询 ProgressStore。
- 客户端断线可重连：用 ``?after_seq=N`` 从断点继续。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator

from fastapi.requests import Request
from fastapi.responses import StreamingResponse

from udify.core.orchestration import TERMINAL_STATUSES, JobStatus, JobStore
from udify.core.orchestration.progress import ProgressStore

# 推送这些状态后关闭流——它们不会产生更多进度事件。
SSE_TERMINAL: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED} | set(TERMINAL_STATUSES)
)

HEARTBEAT_SEC = 1.0
POLL_SEC = 0.5


# 断连后浏览器重连前的等待毫秒数（SSE ``retry:`` 字段）。
RETRY_MS = 2000


def _sse_event(data: dict, event: str = "progress", event_id: int | None = None) -> str:
    """格式化一条 SSE 事件。

    ``event_id`` 会写成 SSE 的 ``id:`` 字段。这是断连恢复的**关键**：EventSource 会
    记住最后一个 id，重连时通过 ``Last-Event-ID`` 请求头回传，服务端据此续传。
    没有 ``id:`` 时浏览器虽然会自动重连，但无从告知断点，断连期间的事件会永久丢失。

    这里 ``id`` 直接用 ``progress_events.seq``——该表本就是 append-only 且带单调 seq，
    因此断连补发**零新增存储**（不需要事件缓冲区，这也是 SSE 相对 WebSocket 的优势：
    WebSocket 得自建补发机制）。
    """
    payload = json.dumps(data, ensure_ascii=False)
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {payload}\n\n"


async def job_events_stream(
    job_id: str,
    store: JobStore,
    progress_store: ProgressStore,
    after_seq: int = 0,
) -> AsyncIterator[str]:
    """生成 SSE chunk 序列。

    先重放 after_seq 之后的历史，再轮询 ProgressStore 获取新事件；
    任务终态时推送 ``done`` 事件并结束。
    """
    last_seq = after_seq

    # 告知客户端重连间隔（浏览器 EventSource 自动遵守）
    yield f"retry: {RETRY_MS}\n\n"

    # 1. 重放历史
    for evt in progress_store.history(job_id, after_seq=after_seq):
        last_seq = max(last_seq, evt.seq)
        yield _sse_event(evt.to_dict(), event_id=evt.seq)

    # 2. 轮询新事件 + 心跳，直到终态
    while True:
        job = store.get(job_id)
        if job is not None and job.status in SSE_TERMINAL:
            # 终态：补推终态后剩余事件，再结束
            for evt in progress_store.history(job_id, after_seq=last_seq):
                last_seq = max(last_seq, evt.seq)
                yield _sse_event(evt.to_dict(), event_id=evt.seq)
            yield _sse_event(
                {"job_id": job_id, "status": job.status.value},
                event="done",
                event_id=last_seq,
            )
            return

        # 推送新事件
        new_events = progress_store.history(job_id, after_seq=last_seq)
        for evt in new_events:
            last_seq = max(last_seq, evt.seq)
            yield _sse_event(evt.to_dict(), event_id=evt.seq)

        # 心跳（SSE comment，不触发客户端 event handler）
        yield ": ping\n\n"
        await asyncio.sleep(POLL_SEC)


def make_job_events_route(prefix: str):
    """构造 SSE 路由处理函数，闭包捕获 ApiState。

    Usage::

        from udify.api.job_events import make_job_events_route
        app.add_api_route(f"{prefix}/jobs/{{job_id}}/events",
                          make_job_events_route(prefix), methods=["GET"])
    """
    from udify.api.app import ApiState  # noqa: PLC0415 — avoid circular import at module load

    async def _route(job_id: str, request: Request, after_seq: int = 0):
        state: ApiState = request.app.state.udify

        # 断点优先取 ``Last-Event-ID`` 头——浏览器 EventSource 自动重连时发的是它，
        # 而不是我们的 ``?after_seq=`` 查询参数。只认查询参数意味着自动重连必然丢事件。
        # 查询参数保留给手动/非浏览器客户端，两者取较大值以免回退重放。
        resume_from = after_seq
        raw_last_id = request.headers.get("last-event-id")
        if raw_last_id:
            # 头部来自客户端，不可信：非法值忽略并退回查询参数，不因此中断连接
            with contextlib.suppress(ValueError):
                resume_from = max(resume_from, int(raw_last_id))
        if state.store.get(job_id) is None:
            return StreamingResponse(
                iter((_sse_event({"error": "job not found", "job_id": job_id}, event="error"),)),
                media_type="text/event-stream",
                status_code=404,
            )
        progress = getattr(state, "progress_store", None)
        if progress is None:
            # ApiState 未注入 progress_store ——返回降级事件
            async def _no_progress() -> AsyncIterator[str]:
                yield _sse_event(
                    {"job_id": job_id, "warning": "progress_store not configured"},
                    event="error",
                )

            return StreamingResponse(_no_progress(), media_type="text/event-stream")

        return StreamingResponse(
            job_events_stream(job_id, state.store, progress, after_seq=resume_from),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲（本机无 nginx，但语义正确）
                "Connection": "keep-alive",
            },
        )

    return _route
