import type { Report } from "@/lib/api";

/** 运行时探针报告（UI-04）：证据优先呈现。 */
export function ProbeView({ report }: { report: Report }) {
  const p = report.probe;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="探针" value={`${p.results.filter((r) => r.passed).length}/${p.probe_count}`} ok={p.passed} />
        <Stat label="游戏可启动" value={p.game_started ? "是" : "否"} ok={p.game_started} />
        <Stat label="状态可读" value={p.state_readable ? "是" : "否"} ok={p.state_readable} />
        <Stat label="Console 错误" value={String(p.console_error_count)} ok={p.console_error_count === 0} />
      </div>

      <ul className="space-y-2">
        {p.results.map((r) => (
          <li key={r.probe_id} className="rounded-sm border border-edge bg-panel px-3 py-2">
            <div className="flex items-center gap-2">
              <span className={`font-mono text-xs ${r.passed ? "text-ok" : "text-err"}`}>
                {r.passed ? "✓" : "✗"}
              </span>
              <span className="font-mono text-xs text-ink">{r.probe_id}</span>
              <span className="ml-auto font-mono text-[10px] uppercase tracking-wider text-faint">
                {r.kind}
              </span>
            </div>
            {r.evidence && (
              <p className="mt-1 font-mono text-[11px] leading-4 text-muted">{r.evidence}</p>
            )}
          </li>
        ))}
      </ul>

      <p className="font-mono text-[10px] text-faint">
        checksum 基线 {short(report.graph_checksum_before)} · 应用于 {short(report.graph_checksum_applied_on)}
      </p>
    </div>
  );
}

function Stat({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="rounded-md border border-edge bg-panel px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-widest text-faint">{label}</div>
      <div className={`font-mono text-lg font-semibold ${ok ? "text-ok" : "text-err"}`}>
        {value}
      </div>
    </div>
  );
}

function short(h: string | null): string {
  return h ? `${h.slice(0, 10)}…` : "—";
}
