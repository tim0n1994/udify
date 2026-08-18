"use client";

import { ChevronRight } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/ui/States";
import type { Job } from "@/lib/api";
import { fmtTime } from "@/lib/ui";
import { cn } from "@/lib/cn";

export function JobTable({
  jobs,
  selectedId,
  hasFilters,
  onSelect,
  onOpen,
}: {
  jobs: Job[];
  selectedId: string | null;
  hasFilters: boolean;
  onSelect: (job: Job) => void;
  onOpen: (job: Job) => void;
}) {
  if (jobs.length === 0) {
    return (
      <EmptyState
        title={hasFilters ? "没有符合筛选条件的任务" : "还没有任务"}
        description={hasFilters ? "清空搜索或更换状态筛选。" : "从上方提交第一个改造意图。"}
      />
    );
  }
  return (
    <div className="data-scroll min-w-0 overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-left" aria-label="任务列表">
        <thead className="bg-bg/50 font-mono text-[11px] text-muted">
          <tr>
            <th className="px-4 py-2.5 font-medium">状态</th>
            <th className="px-4 py-2.5 font-medium">意图</th>
            <th className="px-4 py-2.5 font-medium">游戏目录</th>
            <th className="px-4 py-2.5 font-medium">更新时间</th>
            <th className="w-12"><span className="sr-only">操作</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-edge">
          {jobs.map((job) => {
            const selected = job.job_id === selectedId;
            return (
              <tr
                key={job.job_id}
                tabIndex={0}
                aria-selected={selected}
                className={cn(
                  "density-row cursor-pointer bg-panel transition hover:bg-panel-2",
                  selected && "bg-accent/5 shadow-[inset_2px_0_0_var(--color-accent)]",
                )}
                onClick={() => onSelect(job)}
                onDoubleClick={() => onOpen(job)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") onOpen(job);
                  if (event.key === " ") {
                    event.preventDefault();
                    onSelect(job);
                  }
                }}
              >
                <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                <td className="max-w-[360px] px-4 py-3">
                  <p className="truncate text-[13px] text-ink">{job.intent}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-faint">{job.job_id}</p>
                </td>
                <td className="max-w-[300px] truncate px-4 py-3 font-mono text-[11px] text-muted">
                  {job.game_root}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-mono text-[11px] text-muted">
                  {fmtTime(job.updated_at)}
                </td>
                <td className="px-3 py-3">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      onOpen(job);
                    }}
                    className="rounded-sm p-1 text-faint hover:bg-panel-3 hover:text-accent"
                    aria-label={`打开任务 ${job.job_id}`}
                  >
                    <ChevronRight className="h-4 w-4" aria-hidden />
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
