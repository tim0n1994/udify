import type { Report } from "@/lib/api";

/** 运行时探针报告（UI-04）：证据优先呈现。 */
export function ProbeView({ report }: { report: Report }) {
  const p = report.probe;
  const runtimeMeasured = p.skipped === false && Boolean(report.delivery && report.delivery.tier !== "STATIC_ONLY") &&
    ["NATIVE_HEADLESS", "AUTOMATED_NON_HEADLESS"].includes(report.engine_coverage ?? "");
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="探针" value={runtimeMeasured ? `${p.results.filter((r) => r.passed).length}/${p.probe_count}` : "未执行"} ok={runtimeMeasured ? p.passed : null} />
        <Stat label="游戏可启动" value={runtimeMeasured ? p.game_started ? "是" : "否" : "未验证"} ok={runtimeMeasured ? p.game_started : null} />
        <Stat label="状态可读" value={runtimeMeasured ? p.state_readable ? "是" : "否" : "未验证"} ok={runtimeMeasured ? p.state_readable : null} />
        <Stat label="Console 错误" value={runtimeMeasured ? String(p.console_error_count) : "未采集"} ok={runtimeMeasured ? p.console_error_count === 0 : null} />
      </div>

      {p.reason ? <p className="text-xs text-muted">{p.reason}</p> : null}

      <ul className="space-y-2">
        {p.results.map((r) => (
          <li key={r.probe_id} className="rounded-sm border border-edge bg-panel px-3 py-2">
            <div className="flex items-center gap-2">
              <span className={`font-mono text-xs ${runtimeMeasured ? r.passed ? "text-ok" : "text-err" : "text-muted"}`}>
                {runtimeMeasured ? r.passed ? "✓" : "✗" : "记录未验证"}
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

function Stat({ label, value, ok }: { label: string; value: string; ok: boolean | null }) {
  return (
    <div className="rounded-md border border-edge bg-panel px-3 py-2">
      <div className="font-mono text-[10px] uppercase tracking-widest text-faint">{label}</div>
      <div className={`font-mono text-lg font-semibold ${ok === null ? "text-muted" : ok ? "text-ok" : "text-err"}`}>
        {value}
      </div>
    </div>
  );
}

function short(h: string | null): string {
  return h ? `${h.slice(0, 10)}…` : "—";
}
