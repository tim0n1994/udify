/**
 * iter4 M4 PR3 — useJobProgress(jobId)：SSE 主、轮询兜底的进度订阅。
 *
 * 策略（T4 研究结论）：
 * - 优先 EventSource 连接 /api/v0/jobs/{id}/events，实时接收 ProgressEvent。
 * - EventSource 不可用或连续失败 N 次 → 降级轮询 GET /jobs/{id}?after_seq=N。
 * - 用 after_seq 做断线重连，不丢事件、不重复。
 * - 任务进入终态（done 事件或 status 属于终态集合）→ 停止订阅。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { BUILD_CONFIG } from "@/lib/config/build";
import { call } from "@/lib/api/client";
import { jobDetailSchema } from "@/lib/api/schema";
import {
  progressEventSchema,
  SSE_EVENT_DONE,
  SSE_EVENT_PROGRESS,
  type ProgressEvent_,
} from "@/lib/api/job-progress";
import { ACTIVE_STATUSES } from "@/lib/api/query";

const MAX_SSE_FAILURES = 3;

export interface JobProgressState {
  events: ProgressEvent_[];
  latest: ProgressEvent_ | null;
  isDone: boolean;
  /** 当前是否走 SSE（false = 已降级到轮询）。 */
  usingSse: boolean;
  error: string | null;
}

export function useJobProgress(jobId: string | null | undefined): JobProgressState {
  const [state, setState] = useState<JobProgressState>({
    events: [],
    latest: null,
    isDone: false,
    usingSse: true,
    error: null,
  });
  const failures = useRef(0);
  const lastSeq = useRef(0);
  const closed = useRef(false);

  const appendEvent = useCallback((evt: ProgressEvent_) => {
    if (closed.current) return;
    lastSeq.current = Math.max(lastSeq.current, evt.seq);
    setState((prev) => ({
      ...prev,
      events: [...prev.events, evt],
      latest: evt,
    }));
  }, []);

  const pollFallback = useCallback(
    async (id: string) => {
      // 轮询兜底：GET /jobs/{id} 返回 events，按 after_seq 增量取
      try {
        const detail = await call(
          `/api/v0/jobs/${id}?after_seq=${lastSeq.current}`,
          jobDetailSchema,
        );
        if (closed.current) return;
        for (const e of detail.events) {
          // JobEvent 与 ProgressEvent 形状不同，只取可映射字段
          appendEvent({
            job_id: e.job_id,
            stage: (e.stage as ProgressEvent_["stage"]) ?? "planning",
            detail: e.event,
            pct: 0,
            current: 0,
            total: 0,
            timestamp: new Date(e.ts).toISOString(),
            seq: e.seq,
          });
        }
        if (!ACTIVE_STATUSES.includes(detail.job.status)) {
          setState((prev) => ({ ...prev, isDone: true }));
        }
      } catch {
        setState((prev) => ({ ...prev, error: "polling failed" }));
      }
    },
    [appendEvent],
  );

  useEffect(() => {
    if (!jobId) return;
    closed.current = false;
    setState({ events: [], latest: null, isDone: false, usingSse: true, error: null });
    const base = BUILD_CONFIG.config.apiBase;
    const url = `${base}/api/v0/jobs/${jobId}/events?after_seq=${lastSeq.current}`;

    let es: EventSource | null = null;
    let pollTimer: ReturnType<typeof setInterval> | null = null;

    const startSse = () => {
      try {
        es = new EventSource(url);
      } catch {
        failures.current = MAX_SSE_FAILURES;
        degradeToPoll();
        return;
      }
      es.addEventListener(SSE_EVENT_PROGRESS, (msg) => {
        failures.current = 0;
        try {
          const parsed = progressEventSchema.parse(JSON.parse((msg as MessageEvent).data));
          appendEvent(parsed);
        } catch {
          /* 忽略格式错误的事件，不中断流 */
        }
      });
      es.addEventListener(SSE_EVENT_DONE, () => {
        if (closed.current) return;
        setState((prev) => ({ ...prev, isDone: true }));
        es?.close();
      });
      es.onerror = () => {
        failures.current += 1;
        if (failures.current >= MAX_SSE_FAILURES) {
          es?.close();
          degradeToPoll();
        }
      };
    };

    const degradeToPoll = () => {
      setState((prev) => ({ ...prev, usingSse: false }));
      void pollFallback(jobId);
      pollTimer = setInterval(() => void pollFallback(jobId), 1500);
    };

    startSse();

    return () => {
      closed.current = true;
      es?.close();
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [jobId, appendEvent, pollFallback]);

  return state;
}
