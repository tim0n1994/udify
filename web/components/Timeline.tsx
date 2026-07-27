import type { Job, JobEvent } from "@/lib/api";
import { ACTIVE_STATUSES, fmtTime } from "@/lib/ui";

/** 阶段时间线：读 job_events（OBS-01 trace），当前阶段脉冲。 */
export function Timeline({ job, events }: { job: Job; events: JobEvent[] }) {
  const isActive = ACTIVE_STATUSES.includes(job.status);
  return (
    <ol className="data-scroll max-h-72 space-y-0 overflow-y-auto pr-2">
      {events.map((ev, idx) => {
        const last = idx === events.length - 1;
        const pulse = last && isActive;
        return (
          <li key={ev.seq} className="relative flex gap-3 pb-4 last:pb-0">
            {!last && (
              <span
                className="absolute left-[5px] top-4 h-full w-px bg-edge"
                aria-hidden
              />
            )}
            <span
              className={`relative mt-1 h-[11px] w-[11px] shrink-0 rounded-full border ${
                pulse
                  ? "stage-active border-accent bg-accent"
                  : ev.event === "job_failed"
                    ? "border-err bg-err/60"
                    : "border-edge bg-panel-2"
              }`}
              aria-hidden
            />
            <div className="min-w-0">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-xs text-ink">{ev.event}</span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-faint">
                  {ev.stage}
                </span>
              </div>
              <div className="font-mono text-[10px] text-faint">
                #{ev.seq} · {fmtTime(ev.ts)}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
