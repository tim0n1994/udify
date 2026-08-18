"use client";

import { Activity, CheckCircle2, Radio } from "lucide-react";
import { cn } from "@/lib/cn";
import { useJobProgress } from "@/hooks/use-job-progress";
import type { ProgressStage } from "@/lib/api/job-progress";

const STAGE_ORDER: ProgressStage[] = [
  "perceiving",
  "planning",
  "applying",
  "validating",
  "packaging",
];

const STAGE_LABELS: Record<ProgressStage, string> = {
  perceiving: "感知",
  planning: "规划",
  applying: "应用",
  validating: "验证",
  packaging: "打包",
};

/**
 * iter4 M4 PR3 — 任务进度面板：阶段时间线 + 进度条 + SSE/轮询状态。
 *
 * 从 useJobProgress 订阅实时 ProgressEvent，渲染：
 * - 当前阶段高亮 + 已完成阶段打勾的阶段时间线
 * - 最新事件的百分比进度条
 * - SSE/轮询连接状态指示
 */
export function JobProgressPanel({ jobId }: { jobId: string }) {
  const { events, latest, isDone, usingSse, error } = useJobProgress(jobId);

  const currentStage = latest?.stage ?? null;
  const pct = latest?.pct ?? 0;
  const completedIdx = currentStage ? STAGE_ORDER.indexOf(currentStage) : -1;

  return (
    <section
      className="rounded-sm border border-edge bg-panel-2 p-4"
      aria-label="任务进度"
    >
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent" aria-hidden />
          <h3 className="font-mono text-sm font-semibold text-ink">进度</h3>
        </div>
        <ConnectionBadge usingSse={usingSse} isDone={isDone} error={error} />
      </header>

      {/* 进度条 */}
      <div className="mb-4">
        <div className="mb-1 flex items-center justify-between font-mono text-xs text-muted">
          <span>{currentStage ? STAGE_LABELS[currentStage] : "等待开始"}</span>
          <span>{pct.toFixed(0)}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-panel-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div
            className={cn(
              "h-full rounded-full transition-all duration-300",
              isDone ? "bg-accent" : "bg-accent/70",
            )}
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
        {latest ? (
          <p className="mt-1 truncate font-mono text-xs text-faint" title={latest.detail}>
            {latest.detail || `${latest.current}/${latest.total}`}
          </p>
        ) : null}
      </div>

      {/* 阶段时间线 */}
      <ol className="flex items-center gap-1">
        {STAGE_ORDER.map((stage, idx) => {
          const isCompleted = isDone || (completedIdx >= 0 && idx < completedIdx);
          const isCurrent = stage === currentStage && !isDone;
          return (
            <li key={stage} className="flex flex-1 items-center gap-1">
              <span
                className={cn(
                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border font-mono text-[10px]",
                  isCompleted && "border-accent bg-accent text-bg",
                  isCurrent && "border-accent bg-accent/15 text-accent",
                  !isCompleted && !isCurrent && "border-edge text-faint",
                )}
                aria-label={STAGE_LABELS[stage]}
              >
                {isCompleted ? <CheckCircle2 className="h-3 w-3" aria-hidden /> : idx + 1}
              </span>
              <span
                className={cn(
                  "font-mono text-[11px]",
                  isCurrent ? "text-accent" : isCompleted ? "text-muted" : "text-faint",
                )}
              >
                {STAGE_LABELS[stage]}
              </span>
              {idx < STAGE_ORDER.length - 1 ? (
                <span className="mx-1 h-px flex-1 bg-edge" aria-hidden />
              ) : null}
            </li>
          );
        })}
      </ol>

      {/* 事件流（最近 5 条） */}
      {events.length > 0 ? (
        <ul className="mt-4 space-y-1 border-t border-edge pt-3">
          {events.slice(-5).map((evt) => (
            <li key={evt.seq} className="flex items-center gap-2 font-mono text-[11px] text-muted">
              <span className="text-faint">#{evt.seq}</span>
              <span className="text-accent/80">{STAGE_LABELS[evt.stage] ?? evt.stage}</span>
              <span className="truncate text-faint">{evt.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function ConnectionBadge({
  usingSse,
  isDone,
  error,
}: {
  usingSse: boolean;
  isDone: boolean;
  error: string | null;
}) {
  if (error) {
    return (
      <span className="flex items-center gap-1 font-mono text-[11px] text-err">
        <Radio className="h-3 w-3" aria-hidden />
        轮询
      </span>
    );
  }
  if (isDone) {
    return (
      <span className="flex items-center gap-1 font-mono text-[11px] text-accent">
        <CheckCircle2 className="h-3 w-3" aria-hidden />
        完成
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 font-mono text-[11px] text-muted">
      <span className={cn("h-2 w-2 rounded-full", usingSse ? "bg-accent" : "bg-faint")} aria-hidden />
      {usingSse ? "SSE" : "轮询"}
    </span>
  );
}
