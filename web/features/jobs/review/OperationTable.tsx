"use client";

import { LocateFixed } from "lucide-react";
import type { PatchOp } from "@/lib/api";
import { riskLevel, RISK_COLORS } from "@/lib/ui";
import { cn } from "@/lib/cn";

export function OperationTable({
  operations,
  selectedIndex,
  onSelect,
}: {
  operations: PatchOp[];
  selectedIndex: number | null;
  onSelect: (operation: PatchOp, index: number) => void;
}) {
  return (
    <section className="surface min-w-0 max-w-full overflow-hidden" aria-labelledby="operation-table-title">
      <header className="border-b border-edge px-4 py-3">
        <h2 id="operation-table-title" className="text-sm font-semibold text-ink">
          操作与证据 <span className="font-mono text-[10px] text-faint">（{operations.length} 项）</span>
        </h2>
      </header>
      <div className="data-scroll overflow-x-auto">
        <table className="w-full min-w-[940px] border-collapse text-left text-xs">
          <thead className="bg-bg/50 font-mono text-[10px] text-muted">
            <tr>
              <th className="px-3 py-2 font-medium">#</th><th className="px-3 py-2 font-medium">目标</th>
              <th className="px-3 py-2 font-medium">操作</th><th className="px-3 py-2 font-medium">参数</th>
              <th className="px-3 py-2 font-medium">变更理由</th><th className="px-3 py-2 font-medium">证据 (SourceSpan)</th>
              <th className="px-3 py-2 font-medium">风险</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {operations.map((operation, index) => {
              const level = riskLevel(operation.risk ?? 0);
              const selected = selectedIndex === index;
              return (
                <tr key={`${operation.target_id}-${operation.op_type}-${index}`} className={cn("bg-panel hover:bg-panel-2", selected && "bg-accent/7 ring-1 ring-inset ring-accent")}>
                  <td className="px-3 py-2.5 font-mono text-faint">{index + 1}</td>
                  <td className="max-w-[160px] px-3 py-2.5 font-mono text-[11px] text-ink">{operation.target_id}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-ink">{operation.op_type}</td>
                  <td className="max-w-[220px] px-3 py-2.5 font-mono text-[10px] text-muted">
                    {Object.entries(operation.payload).map(([key, value]) => (
                      <div key={key} className="truncate"><span className="text-faint">{key}=</span>{JSON.stringify(value)}</div>
                    ))}
                  </td>
                  <td className="max-w-[250px] px-3 py-2.5 leading-5 text-muted">{operation.planning_reason || "—"}</td>
                  <td className="px-3 py-2.5">
                    {operation.source_span ? (
                      <button
                        type="button"
                        onClick={() => onSelect(operation, index)}
                        className="inline-flex max-w-[240px] items-center gap-1 border border-edge-strong bg-bg/50 px-2 py-1 font-mono text-[10px] text-muted hover:border-accent hover:text-accent"
                      >
                        <LocateFixed className="h-3 w-3 shrink-0" aria-hidden />
                        <span className="truncate">
                          {operation.source_span.line_start == null
                            ? `${operation.source_span.file_path} · 文件级证据（无行号）`
                            : `${operation.source_span.file_path}:${operation.source_span.line_start}-${operation.source_span.line_end ?? operation.source_span.line_start}`}
                        </span>
                      </button>
                    ) : <span className="text-[11px] text-faint">无可定位 SourceSpan</span>}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex border px-2 py-0.5 font-mono text-[10px] ${RISK_COLORS[level]}`} title={`risk ${(operation.risk ?? 0).toFixed(2)}`}>R{level}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
