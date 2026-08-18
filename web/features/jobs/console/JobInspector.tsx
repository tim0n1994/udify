import { ExternalLink, Folder, ShieldCheck } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/Button";
import type { Job } from "@/lib/api";
import { fmtTime, shortHash } from "@/lib/ui";

export function JobInspector({ job, onOpen }: { job: Job | null; onOpen: () => void }) {
  return (
    <aside className="hidden border-l border-edge bg-panel-2/30 p-5 xl:block" aria-label="任务详情">
      {job ? (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">任务详情</h3>
            <span className="font-mono text-[10px] text-faint">{job.job_id}</span>
          </div>
          <StatusBadge status={job.status} />
          <dl className="space-y-4 text-xs">
            <div><dt className="control-label">意图</dt><dd className="mt-1 leading-5 text-ink">{job.intent}</dd></div>
            <div>
              <dt className="control-label">游戏目录</dt>
              <dd className="mt-1 flex gap-2 break-all font-mono text-[11px] leading-5 text-muted">
                <Folder className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {job.game_root}
              </dd>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><dt className="control-label">创建</dt><dd className="mt-1 font-mono text-[11px] text-muted">{fmtTime(job.created_at)}</dd></div>
              <div><dt className="control-label">更新</dt><dd className="mt-1 font-mono text-[11px] text-muted">{fmtTime(job.updated_at)}</dd></div>
            </div>
            <div><dt className="control-label">图基线</dt><dd className="mt-1 font-mono text-[11px] text-muted">{shortHash(job.checkpoint.graph_checksum as string | undefined)}</dd></div>
          </dl>
          <div className="border border-edge bg-bg/50 p-3 text-xs text-muted">
            <div className="flex gap-2">
              <ShieldCheck className="h-4 w-4 shrink-0 text-ok" aria-hidden />
              <p>修改只会进入 VFS 和 ModPackage，原 game_root 保持不变。</p>
            </div>
          </div>
          <Button type="button" variant="primary" className="w-full" onClick={onOpen}>
            <ExternalLink className="h-4 w-4" aria-hidden /> 打开任务
          </Button>
        </div>
      ) : (
        <p className="text-sm text-faint">选择一条任务查看摘要。</p>
      )}
    </aside>
  );
}
