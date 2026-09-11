"use client";

import { Activity, Radio } from "lucide-react";
import { useJobProgress } from "@/hooks/use-job-progress";
import type { JobStatus } from "@/lib/api";
import { STATUS_META, fmtTime } from "@/lib/ui";

interface JobProgressPanelProps {
  jobId: string;
  lifecycleKey?: string;
  status?: JobStatus;
}

export function JobProgressPanel({ jobId, lifecycleKey, status }: JobProgressPanelProps): React.JSX.Element {
  const progress = useJobProgress(jobId, lifecycleKey, status);
  const current = progress.status;
  const meta = current ? STATUS_META[current] : null;
  return (
    <section className="border-y border-edge py-4" aria-label="任务进度" aria-live="polite">
      <div className="flex flex-wrap items-center gap-3">
        <Activity className="h-4 w-4 text-accent" aria-hidden />
        <h2 className="text-sm font-semibold text-ink">任务进度</h2>
        <span className={current === "failed" ? "text-sm text-err" : "text-sm text-ink"}>
          {meta?.label ?? "等待开始"}
        </span>
        <span className="ml-auto inline-flex items-center gap-1 font-mono text-[11px] text-muted">
          <Radio className="h-3 w-3" aria-hidden />
          {progress.isDone ? "订阅已结束" : progress.usingSse ? progress.connected ? "实时连接" : "正在连接" : "轮询"}
        </span>
      </div>
      {progress.error ? <p role="status" className="mt-2 text-xs text-err">{progress.error}</p> : null}
      {progress.events.length ? (
        <ol className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
          {progress.events.slice(-5).map((event) => (
            <li key={event.seq} className="min-w-0 text-xs text-muted">
              <span className="font-mono text-faint">#{event.seq} {fmtTime(event.ts)}</span>
              <span className="ml-2 break-all">{event.event}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
