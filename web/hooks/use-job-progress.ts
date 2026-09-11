"use client";

import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useConfig } from "@/lib/config";
import { call } from "@/lib/api/client";
import { jobDetailSchema, jobEventSchema, jobStatusSchema } from "@/lib/api/schema";
import { jobDoneSchema } from "@/lib/api/job-progress";
import { queryKeys } from "@/lib/api/query";
import { isTerminalStatus, mergeJobEvents } from "@/lib/api/job-event-state";
import type { JobEvent, JobStatus } from "@/lib/api/types";

export interface JobProgressState {
  events: JobEvent[];
  latest: JobEvent | null;
  status: JobStatus | null;
  isDone: boolean;
  usingSse: boolean;
  connected: boolean;
  error: string | null;
}

function emptyState(status: JobStatus | null = null): JobProgressState {
  return { events: [], latest: null, status, isDone: isTerminalStatus(status), usingSse: true, connected: false, error: null };
}

/** Both transports consume the persisted JobStore sequence. Each subscription owns its requests. */
export function useJobProgress(
  jobId: string | null | undefined,
  lifecycleKey = "",
  initialStatus?: JobStatus,
): JobProgressState {
  const { config } = useConfig();
  const queryClient = useQueryClient();
  const [state, setState] = useState<JobProgressState>(emptyState);
  const initial = useRef(initialStatus);
  initial.current = initialStatus;

  useEffect(() => {
    setState(emptyState(initial.current ?? null));
    if (!jobId) return;
    let alive = true;
    let seq = 0;
    let events: JobEvent[] = [];
    let status = initial.current ?? null;
    let failures = 0;
    let polling = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let es: EventSource | undefined;
    const controller = new AbortController();

    const invalidate = () => {
      for (const queryKey of [queryKeys.job(jobId), queryKeys.jobs, queryKeys.report(jobId), queryKeys.plan(jobId)]) {
        void queryClient.invalidateQueries({ queryKey });
      }
    };
    const stop = () => {
      es?.close();
      clearTimeout(timer);
    };
    const update = (incoming: JobEvent[], nextStatus: JobStatus | null) => {
      if (!alive) return;
      const merged = mergeJobEvents(events, incoming, jobId);
      const nextSeq = merged.at(-1)?.seq ?? seq;
      const changed = nextSeq !== seq || status !== nextStatus;
      events = merged;
      seq = nextSeq;
      status = nextStatus;
      setState((prev) => ({ ...prev, events, latest: events.at(-1) ?? null, status, isDone: isTerminalStatus(status), connected: isTerminalStatus(status) ? false : prev.connected, error: null }));
      if (changed) invalidate();
      if (isTerminalStatus(status)) stop();
    };
    const snapshot = async () => {
      try {
        const detail = await call(`/api/v0/jobs/${jobId}?after_seq=${seq}`, jobDetailSchema,
          { signal: controller.signal }, config.apiBase);
        if (!alive || detail.job.job_id !== jobId) return;
        // An older in-flight snapshot must not roll a newer SSE status backward.
        const newest = detail.events.at(-1)?.seq ?? 0;
        update(detail.events, newest >= seq ? detail.job.status : status);
      } catch {
        if (alive) setState((prev) => ({ ...prev, error: "暂时无法读取任务状态" }));
      }
    };
    const poll = async () => {
      await snapshot();
      if (alive && polling && !isTerminalStatus(status)) timer = setTimeout(() => void poll(), 1500);
    };
    const degrade = () => {
      if (!alive || polling || isTerminalStatus(status)) return;
      polling = true;
      es?.close();
      setState((prev) => ({ ...prev, usingSse: false, connected: false }));
      void poll();
    };

    void snapshot();
    if (!isTerminalStatus(status) || lifecycleKey !== "") {
      try {
        es = new EventSource(`${config.apiBase}/api/v0/jobs/${jobId}/events?after_seq=0`);
        es.onopen = () => { if (alive) setState((prev) => ({ ...prev, connected: true })); };
        es.addEventListener("job", (message) => {
          if (!alive) return;
          try {
            const event = jobEventSchema.parse(JSON.parse((message as MessageEvent).data));
            if (event.job_id !== jobId || event.seq <= seq) return;
            failures = 0;
            const parsedStatus = jobStatusSchema.safeParse(event.stage);
            update([event], parsedStatus.success ? parsedStatus.data : status);
          } catch {
            degrade();
          }
        });
        es.addEventListener("done", (message) => {
          if (!alive) return;
          try {
            const done = jobDoneSchema.parse(JSON.parse((message as MessageEvent).data));
            if (done.job_id !== jobId || done.seq < seq) return;
            update([], done.status);
            void snapshot();
          } catch {
            degrade();
          }
        });
        es.onerror = () => {
          if (!alive) return;
          setState((prev) => ({ ...prev, connected: false }));
          failures += 1;
          if (failures >= 3) degrade();
        };
      } catch {
        degrade();
      }
    }
    return () => {
      alive = false;
      stop();
      controller.abort();
    };
  }, [jobId, lifecycleKey, config.apiBase, queryClient]);

  return state;
}
