import type { JobStatus } from "@/lib/api";
import { STATUS_META } from "@/lib/ui";

const TONE_CLASSES: Record<string, string> = {
  active: "text-accent border-accent/50 bg-accent/10",
  gate: "text-accent border-accent bg-accent/15 font-semibold",
  ok: "text-ok border-ok/50 bg-ok/10",
  err: "text-err border-err/50 bg-err/10",
  muted: "text-muted border-edge bg-panel",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 font-mono text-xs tracking-wider ${TONE_CLASSES[meta.tone]}`}
    >
      {meta.tone === "active" && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden />
      )}
      {meta.label}
    </span>
  );
}
