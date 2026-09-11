import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import type { Report } from "@/lib/api";

interface ReportEvidenceProps { report: Report }

const GATE_LABELS: Record<string, string> = {
  intent_grounding: "目标确认门",
  sandbox: "隔离执行门",
  runtime_validation: "运行验证门",
  dependency: "依赖兼容门",
  latency: "耗时策略门",
};
const LIFECYCLE_LABELS: Record<string, string> = {
  pending: "待决策", running: "决策中", decided: "已决策",
};

function gateOutcome(gate: NonNullable<Report["gate_verdict"]>["gates"][number], packageOnly: boolean): string {
  if (gate.name === "dependency" && packageOnly) return "未评估（仅生成包）";
  if (gate.verdict === "pass") return gate.delivery_tier < 3 ? "允许降级交付" : "策略允许";
  if (gate.verdict === "fail") return "阻断交付";
  if (gate.verdict === "needs_clarification") return "待确认目标";
  return gate.verdict;
}

export function ReportEvidence({ report }: ReportEvidenceProps): React.JSX.Element {
  const delivery = report.delivery;
  const staticOnly = delivery?.tier === "STATIC_ONLY";
  return (
    <section className="space-y-4 border-b border-edge pb-5" aria-label="交付证据">
      <h2 className="text-sm font-semibold text-ink">交付与验证范围</h2>
      <div className="flex items-start gap-3 border border-edge p-3 text-sm text-muted">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div className="min-w-0 space-y-1">
          <p className="font-semibold text-ink">{delivery ? "仅生成 Mod 包，未安装到游戏" : "交付范围未知"}</p>
          <p>{staticOnly ? "仅进行静态检查，未运行游戏验证。" : delivery?.reason ?? "此报告未记录交付等级，不能确认运行时验证。"}</p>
          {staticOnly ? <p>{delivery.reason}</p> : null}
          <p className="break-words">验证覆盖：{report.engine_coverage ?? "未知"} · 交付等级：{delivery?.tier ?? "未知"}</p>
        </div>
      </div>
      {report.artifact_validation ? (
        <div>
          <h3 className="text-sm font-medium text-ink">产物检查：{report.artifact_validation.passed ? "通过" : "未通过"}</h3>
          <ul className="mt-2 divide-y divide-edge">
            {report.artifact_validation.checks.map((check, index) => (
              <li key={`${check.name}-${index}`} className="flex gap-2 py-2 text-xs">
                {check.passed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-label="通过" /> : <XCircle className="h-4 w-4 shrink-0 text-err" aria-label="未通过" />}
                <span className="min-w-0 break-words text-muted"><strong className="text-ink">{check.name}</strong> {check.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : <p className="text-xs text-muted">产物检查证据未记录。</p>}
      {report.gate_verdict ? (
        <div>
          <h3 className="text-sm font-medium text-ink">执行闸门</h3>
          <p className="mt-1 break-words text-xs text-muted">{report.gate_verdict.final_tier_reason}</p>
          <ul className="mt-2 divide-y divide-edge">
            {report.gate_verdict.gates.map((gate, index) => (
              <li key={`${gate.name}-${index}`} className="py-2 text-xs text-muted">
                <p className="break-words"><strong className="text-ink">{GATE_LABELS[gate.name] ?? gate.name}</strong> · {gateOutcome(gate, delivery?.kind === "package" && delivery.installed === false)} · {LIFECYCLE_LABELS[gate.lifecycle] ?? gate.lifecycle}</p>
                <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[11px]">{typeof gate.evidence === "string" ? gate.evidence : JSON.stringify(gate.evidence, null, 2)}</pre>
              </li>
            ))}
          </ul>
        </div>
      ) : <p className="text-xs text-muted">闸门证据未记录。</p>}
      {report.artifacts?.length ? <ul className="space-y-1 text-xs text-muted">{report.artifacts.map((artifact) => <li key={artifact.name} className="break-all">{artifact.name} <span className="font-mono">SHA-256 {artifact.sha256}</span></li>)}</ul> : null}
    </section>
  );
}
