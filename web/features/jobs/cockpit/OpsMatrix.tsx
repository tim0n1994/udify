"use client";

import { useRouter } from "next/navigation";
import type { Job } from "@/lib/api";
import { buildHeatCells, type HeatCellTone } from "@/lib/heat";
import { cn } from "@/lib/cn";

const TONE: Record<HeatCellTone, { text: string; active: string }> = {
  gate: { text: "text-accent", active: "shadow-[inset_0_0_0_1px_var(--color-accent)]" },
  active: { text: "text-r2", active: "shadow-[inset_0_0_0_1px_var(--color-r2)]" },
  ok: { text: "text-ok", active: "shadow-[inset_0_0_0_1px_var(--color-ok)]" },
  err: { text: "text-err", active: "shadow-[inset_0_0_0_1px_var(--color-err)]" },
  idle: { text: "text-muted", active: "" },
};

/** C-03 Ops 热力矩阵：11 个状态格。数量即热度，点击回溯到对应任务。 */
export function OpsMatrix({ jobs }: { jobs: Job[] | undefined }) {
  const router = useRouter();
  const cells = buildHeatCells(jobs ?? []);
  return (
    <div
      role="grid"
      aria-label="任务状态热力矩阵"
      className="grid grid-cols-2 gap-px border border-edge bg-edge sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-11"
    >
      {cells.map((cell) => {
        const count = cell.jobs.length;
        const hot = count > 0 && (cell.tone === "gate" || cell.tone === "active" || cell.tone === "err");
        const first = cell.jobs[0];
        return (
          <button
            key={cell.status}
            role="gridcell"
            type="button"
            disabled={count === 0}
            onClick={() => first && router.push(`/jobs/${first.job_id}`)}
            aria-label={`${cell.label} ${count} 条任务${count > 0 ? "，打开最新一条" : ""}`}
            className={cn(
              "relative flex min-h-[74px] flex-col justify-between bg-vellum px-2.5 py-2 text-left transition",
              count > 0 && "hover:bg-panel-3 focus-visible:bg-panel-3",
              hot && "scanline",
              hot && TONE[cell.tone].active,
            )}
          >
            <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-faint">
              {cell.label}
            </span>
            <span
              className={cn(
                "font-[family-name:var(--font-display)] text-2xl font-semibold leading-none tabular-nums",
                count > 0 ? TONE[cell.tone].text : "text-faint",
              )}
            >
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
