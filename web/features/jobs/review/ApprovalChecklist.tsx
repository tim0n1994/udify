import { CheckCircle2, CircleAlert, Info } from "lucide-react";
import type { Plan } from "@/lib/api";

export function ApprovalChecklist({ plan, auditValid }: { plan: Plan; auditValid: boolean }) {
  const locatableEvidence = plan.operations.filter(
    (operation) => operation.source_span?.line_start != null,
  ).length;
  const checks = [
    { label: `差异范围可见（${plan.diffs.length} 个文件）`, passed: plan.diffs.length > 0 },
    {
      label: `可定位 SourceSpan ${locatableEvidence}/${plan.operations.length}`,
      passed: locatableEvidence === plan.operations.length,
    },
    { label: "Job 审计链完整", passed: auditValid },
    { label: `静态阻塞 ${plan.static_validation.error_count} 条`, passed: plan.static_validation.passed },
  ];
  return (
    <section className="p-4" aria-labelledby="approval-checklist-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="approval-checklist-title" className="text-sm font-semibold text-ink">批准前检查</h2>
        <span className="font-mono text-[10px] text-faint">UI 审阅提示</span>
      </div>
      <ul className="mt-3 divide-y divide-edge">
        {checks.map((check) => (
          <li key={check.label} className="flex items-center gap-2 py-2 text-xs text-muted">
            {check.passed ? <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-hidden /> : <CircleAlert className="h-4 w-4 shrink-0 text-r2" aria-hidden />}
            {check.label}
          </li>
        ))}
      </ul>
      <p className="mt-3 flex gap-2 border border-edge bg-bg/50 p-2.5 text-[11px] leading-5 text-faint">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        该清单不是授权或风险决策；批准资格与状态迁移仍由后端判定。
      </p>
    </section>
  );
}
