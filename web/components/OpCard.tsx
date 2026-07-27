import type { PatchOp } from "@/lib/api";
import { RISK_COLORS, riskLevel } from "@/lib/ui";

/** 操作卡片：op + 风险档位 + 规划理由 + SourceSpan 证据（判据 #5）。 */
export function OpCard({ op, index }: { op: PatchOp; index: number }) {
  const level = riskLevel(op.risk ?? 0);
  return (
    <article className="rounded-md border border-edge bg-panel p-4">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] text-faint">#{index + 1}</span>
        <span className="rounded-sm border border-edge bg-panel-2 px-2 py-0.5 font-mono text-xs text-ink">
          {op.op_type}
        </span>
        {op.execution_mode && (
          <span className="rounded-sm border border-edge px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
            {op.execution_mode}
          </span>
        )}
        <span
          className={`ml-auto rounded-sm border px-2 py-0.5 font-mono text-xs font-semibold ${RISK_COLORS[level]}`}
          title={`启发式风险分 ${(op.risk ?? 0).toFixed(2)}`}
        >
          R{level}
        </span>
      </header>

      <div className="mb-2 font-mono text-xs text-accent">{op.target_id}</div>

      <dl className="mb-3 grid gap-1">
        {Object.entries(op.payload).map(([k, v]) => (
          <div key={k} className="flex gap-2 font-mono text-xs">
            <dt className="w-28 shrink-0 text-faint">{k}</dt>
            <dd className="break-all text-ink">{JSON.stringify(v)}</dd>
          </div>
        ))}
      </dl>

      {op.planning_reason && (
        <p className="mb-2 border-l-2 border-accent/40 pl-2 text-xs text-muted">
          {op.planning_reason}
        </p>
      )}

      {op.source_span && (
        <p className="font-mono text-[10px] text-faint">
          证据 → {op.source_span.file_path}
          {op.source_span.line_start != null && `:${op.source_span.line_start}`}
          {op.source_span.line_end != null &&
            op.source_span.line_end !== op.source_span.line_start &&
            `-${op.source_span.line_end}`}
        </p>
      )}
    </article>
  );
}
