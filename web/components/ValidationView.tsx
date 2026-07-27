import type { StaticValidation } from "@/lib/api";

/** 静态验证结果（VAL-STATIC-01..05 输出）。 */
export function ValidationView({ v }: { v: StaticValidation }) {
  return (
    <div className="space-y-3">
      <div
        className={`flex items-center justify-between rounded-md border px-4 py-3 ${
          v.passed ? "border-ok/40 bg-ok/10" : "border-err/40 bg-err/10"
        }`}
      >
        <span className={`font-mono text-sm font-semibold ${v.passed ? "text-ok" : "text-err"}`}>
          {v.passed ? "静态验证通过" : `阻塞错误 ${v.error_count} 条`}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
          confidence {v.confidence.toFixed(2)} · {v.recommended_action}
        </span>
      </div>

      {v.blocking_errors.map((f, i) => (
        <Finding key={`e${i}`} tone="err" check={f.check} message={f.message} target={f.target_id} />
      ))}
      {v.warnings.map((f, i) => (
        <Finding key={`w${i}`} tone="warn" check={f.check} message={f.message} target={f.target_id} />
      ))}
    </div>
  );
}

function Finding({
  tone,
  check,
  message,
  target,
}: {
  tone: "err" | "warn";
  check: string;
  message: string;
  target: string;
}) {
  return (
    <div
      className={`rounded-sm border px-3 py-2 text-xs ${
        tone === "err" ? "border-err/40 bg-err/5" : "border-r2/40 bg-r2/5"
      }`}
    >
      <span className={`mr-2 font-mono ${tone === "err" ? "text-err" : "text-r2"}`}>
        [{check}]
      </span>
      <span className="text-ink">{message}</span>
      {target && <span className="ml-2 font-mono text-faint">{target}</span>}
    </div>
  );
}
