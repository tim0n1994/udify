"use client";

import { Command, Volume2, VolumeX } from "lucide-react";
import { HealthDot } from "@/components/HealthDot";
import type { Job } from "@/lib/api";
import { ACTIVE_STATUSES } from "@/lib/api";
import { useSound } from "@/lib/sound";

/** C-01 使命条：健康点 + 实时计数 + ⌘K + 声音。驾驶舱的全局态势感知。 */
export function MissionStrip({
  jobs,
  onOpenCommand,
}: {
  jobs: Job[] | undefined;
  onOpenCommand: () => void;
}) {
  const sound = useSound();
  const active = jobs?.filter((job) => ACTIVE_STATUSES.includes(job.status)).length ?? 0;
  const gate = jobs?.filter((job) => job.status === "awaiting_review").length ?? 0;
  return (
    <div className="dossier flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
      <HealthDot />
      <span className="h-4 w-px bg-edge" aria-hidden />
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-faint">
        {active} 活跃 · {gate} 待批准 · {jobs?.length ?? "…"} 总任务
      </span>
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenCommand}
          className="inline-flex min-h-8 items-center gap-2 border border-edge bg-bg/60 px-2.5 font-mono text-[11px] text-muted transition hover:border-muted hover:text-ink"
          aria-label="打开命令面板"
        >
          <Command className="h-3.5 w-3.5" aria-hidden />
          <span className="hidden sm:inline">检索 / 跳转</span>
          <kbd className="border border-edge px-1 text-[9px] text-faint">⌘K</kbd>
        </button>
        <button
          type="button"
          onClick={sound.toggle}
          aria-pressed={sound.enabled}
          aria-label={sound.enabled ? "关闭音效" : "开启音效"}
          title={sound.enabled ? "音效开" : "音效关"}
          className="inline-flex min-h-8 w-8 items-center justify-center border border-edge bg-bg/60 text-muted transition hover:border-muted hover:text-ink"
        >
          {sound.enabled ? (
            <Volume2 className="h-3.5 w-3.5 text-accent" aria-hidden />
          ) : (
            <VolumeX className="h-3.5 w-3.5" aria-hidden />
          )}
        </button>
      </div>
    </div>
  );
}
