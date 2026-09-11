"""SSE replay of the durable JobEvent log returned by job detail polling."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from fastapi import Query
from fastapi.requests import Request
from fastapi.responses import StreamingResponse

from udify.core.orchestration import JobStatus, JobStore

SSE_TERMINAL: frozenset[JobStatus] = frozenset(
    {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.REJECTED, JobStatus.ROLLED_BACK}
)
POLL_SEC = 0.5
RETRY_MS = 2000


def _sse_event(data: dict[str, Any], event: str = "job", event_id: int | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {payload}\n\n"


async def job_events_stream(
    job_id: str,
    store: JobStore,
    after_seq: int = 0,
) -> AsyncIterator[str]:
    """Replay persisted events and tail updates until a terminal state."""
    last_seq = after_seq
    yield f"retry: {RETRY_MS}\n\n"
    while True:
        job, events, _ = store.read_detail(job_id, after_seq=last_seq)
        for evt in events:
            last_seq = evt.seq
            yield _sse_event(evt.to_dict(), event_id=evt.seq)
        if job is not None and job.status in SSE_TERMINAL:
            yield _sse_event(
                {"job_id": job_id, "status": job.status.value, "seq": last_seq},
                event="done",
                event_id=last_seq,
            )
            return
        yield ": ping\n\n"
        await asyncio.sleep(POLL_SEC)


def make_job_events_route(
    prefix: str,
) -> Callable[..., Awaitable[StreamingResponse]]:
    """Build the route with automatic EventSource reconnection support."""
    from udify.api.app import ApiState  # noqa: PLC0415

    async def _route(
        job_id: str, request: Request, after_seq: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        state: ApiState = request.app.state.udify
        resume_from = after_seq
        raw_last_id = request.headers.get("last-event-id")
        if raw_last_id is not None and raw_last_id.isascii() and raw_last_id.isdecimal():
            resume_from = int(raw_last_id)
        if state.store.get(job_id) is None:
            return StreamingResponse(
                iter((_sse_event({"error": "job not found", "job_id": job_id}, event="error"),)),
                media_type="text/event-stream",
                status_code=404,
            )
        return StreamingResponse(
            job_events_stream(job_id, state.store, after_seq=resume_from),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return _route
