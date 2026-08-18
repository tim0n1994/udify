"use client";

import { Fingerprint } from "lucide-react";
import type { JobEvent } from "@/lib/api";

/**
 * 审计条约章：把 JobStore 链式哈希（ORCH-JOB-04）演成纸面印章。
 * 哈希前八位 + 事件计数 + glow 呼吸；链失配则红色告警脉冲。
 */
export function AuditTreatySeal({
  valid,
  events,
  jobId,
}: {
  valid: boolean | null;
  events: JobEvent[];
  jobId: string | null;
}) {
  if (!jobId) {
    return (
      <span className="inline-flex items-center gap-2 border border-edge px-2.5 py-1 font-mono text-[10px] tracking-widest text-faint">
        <Fingerprint className="h-3 w-3" aria-hidden /> 审计链 · 待命
      </span>
    );
  }
  const latest = events.at(-1);
  return (
    <span
      className="treaty-seal inline-flex items-center gap-2 px-2.5 py-1 font-mono text-[10px] tracking-widest"
      data-valid={valid !== false}
      role="status"
      aria-label={
        valid === false
          ? `任务 ${jobId} 审计链校验失败`
          : `任务 ${jobId} 审计链完整，${events.length} 条事件`
      }
    >
      <Fingerprint className="h-3 w-3" aria-hidden />
      <span>
        {valid === false ? "链失配" : "链完整"} · {events.length} 事件
      </span>
      {latest ? <span aria-hidden>#{latest.seq} {latest.record_hash.slice(0, 8)}</span> : null}
    </span>
  );
}
