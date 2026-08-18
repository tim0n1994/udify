"use client";

import { Ban, CheckCircle2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import type { Job, Plan } from "@/lib/api";
import { riskLevel } from "@/lib/ui";

export function JobActions({
  job,
  plan,
  highestRisk,
  approvePending,
  rejectPending,
  rollbackPending,
  onApprove,
  onReject,
  onRollback,
}: {
  job: Job;
  plan: Plan;
  highestRisk: number;
  approvePending: boolean;
  rejectPending: boolean;
  rollbackPending: boolean;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onRollback: () => void;
}) {
  const [reason, setReason] = useState("审阅后拒绝");
  const details = (
    <dl className="grid grid-cols-2 gap-2 font-mono text-[11px] text-muted">
      <div><dt className="text-faint">操作</dt><dd>{plan.operations.length}</dd></div>
      <div><dt className="text-faint">文件</dt><dd>{plan.diffs.length}</dd></div>
      <div><dt className="text-faint">最高风险</dt><dd>R{riskLevel(highestRisk)}</dd></div>
      <div><dt className="text-faint">静态阻塞</dt><dd>{plan.static_validation.error_count}</dd></div>
    </dl>
  );
  return (
    <div className="border-t border-edge p-4">
      {job.status === "awaiting_review" ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <ConfirmDialog
            trigger={<Button type="button" variant="danger" className="w-full"><Ban className="h-4 w-4" aria-hidden /> 拒绝计划</Button>}
            title="拒绝这个修改计划？"
            description="任务将进入 rejected 终态，不会应用到 VFS。"
            details={<label className="control-label block">拒绝原因<Input className="mt-2" value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
            confirmLabel="确认拒绝"
            danger
            pending={rejectPending}
            onConfirm={() => onReject(reason.trim() || "审阅后拒绝")}
          />
          <ConfirmDialog
            trigger={<Button type="button" variant="primary" className="w-full" disabled={!plan.static_validation.passed}><CheckCircle2 className="h-4 w-4" aria-hidden /> 批准并应用</Button>}
            title="批准并应用到 VFS？"
            description="后端将再次校验图版本与状态门，然后验证并生成可回滚 ModPackage。原始游戏文件保持不变。"
            details={details}
            confirmLabel="确认批准"
            pending={approvePending}
            onConfirm={onApprove}
          />
        </div>
      ) : null}
      {job.status === "completed" ? (
        <ConfirmDialog
          trigger={<Button type="button" variant="danger" className="w-full"><RotateCcw className="h-4 w-4" aria-hidden /> 回滚并作废包</Button>}
          title="回滚已完成任务？"
          description="后端将作废 ModPackage 并校验 game_root checksum。"
          confirmLabel="确认回滚"
          danger
          pending={rollbackPending}
          onConfirm={onRollback}
        />
      ) : null}
      {["rejected", "rolled_back", "failed"].includes(job.status) ? (
        <p className="text-xs leading-5 text-muted">当前为 <span className="font-mono text-ink">{job.status}</span> 终态，无可执行审批动作。</p>
      ) : null}
    </div>
  );
}
