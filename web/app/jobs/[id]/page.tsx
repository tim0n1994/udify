"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { ACTIVE_STATUSES, fmtTime, shortHash } from "@/lib/ui";
import { DiffView } from "@/components/DiffView";
import { OpCard } from "@/components/OpCard";
import { ProbeView } from "@/components/ProbeView";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { ValidationView } from "@/components/ValidationView";

type Tab = "plan" | "diff" | "report";

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("diff");
  const [actionError, setActionError] = useState<ApiError | null>(null);

  const detail = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.getJob(id),
    refetchInterval: (q) => {
      const status = q.state.data?.job.status;
      return status && ACTIVE_STATUSES.includes(status) ? 1000 : false;
    },
  });

  const job = detail.data?.job;
  const planReady =
    job &&
    ["awaiting_review", "applying", "validating", "packaging", "completed", "rolled_back"].includes(
      job.status,
    );
  const reportReady = job && ["completed", "rolled_back", "failed"].includes(job.status);

  const plan = useQuery({
    queryKey: ["plan", id],
    queryFn: () => api.getPlan(id),
    enabled: Boolean(planReady),
  });
  const report = useQuery({
    queryKey: ["report", id],
    queryFn: () => api.getReport(id),
    enabled: Boolean(reportReady),
    retry: false,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["job", id] });
    qc.invalidateQueries({ queryKey: ["report", id] });
    qc.invalidateQueries({ queryKey: ["jobs"] });
  };
  const onError = (e: unknown) => setActionError(e instanceof ApiError ? e : null);

  const approve = useMutation({
    mutationFn: () => api.approve(id),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError,
  });
  const reject = useMutation({
    mutationFn: () => api.reject(id, "reviewer rejected"),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError,
  });
  const rollback = useMutation({
    mutationFn: () => api.rollback(id),
    onSuccess: () => {
      setActionError(null);
      invalidate();
    },
    onError,
  });

  if (detail.isError) {
    const e = detail.error;
    return (
      <div className="rounded-md border border-err/40 bg-err/10 px-4 py-6 text-sm">
        <p className="font-mono text-err">
          {e instanceof ApiError ? e.record.code : "加载失败"}
        </p>
        <p className="mt-1 text-ink">{e instanceof ApiError ? e.record.message : String(e)}</p>
        <Link href="/" className="mt-3 inline-block font-mono text-xs text-accent underline">
          ← 返回控制台
        </Link>
      </div>
    );
  }
  if (!job) return <p className="font-mono text-sm text-faint">加载中…</p>;

  return (
    <div className="space-y-6">
      {/* 头部 */}
      <header className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-3">
            <Link href="/" className="font-mono text-xs text-faint hover:text-accent">
              ←
            </Link>
            <span className="font-mono text-xs text-faint">{job.job_id}</span>
            <StatusBadge status={job.status} />
            {detail.data && !detail.data.audit_chain_valid && (
              <span className="rounded-sm border border-err bg-err/15 px-2 py-0.5 font-mono text-[10px] text-err">
                审计链校验失败
              </span>
            )}
          </div>
          <h1 className="truncate text-xl font-semibold text-ink">{job.intent}</h1>
          <p className="mt-1 font-mono text-[11px] text-faint">
            {job.game_root} · 创建于 {fmtTime(job.created_at)} · 图基线{" "}
            {shortHash(job.checkpoint["graph_checksum"] as string | undefined)}
          </p>
        </div>
      </header>

      {/* 失败卡（ErrorRecord 完整呈现） */}
      {job.error && job.status === "failed" && (
        <div className="rounded-md border border-err/40 bg-err/10 px-4 py-3 text-sm">
          <p className="font-mono text-xs text-err">{job.error.code}</p>
          <p className="mt-1 text-ink">{job.error.message}</p>
          {job.error.suggested_action && (
            <p className="mt-1 text-xs text-muted">→ {job.error.suggested_action}</p>
          )}
          <p className="mt-1 font-mono text-[10px] text-faint">
            owner: {job.error.owner_module} · {job.error.retryable ? "可重试" : "不可重试"}
          </p>
        </div>
      )}
      {actionError && (
        <div className="rounded-md border border-err/40 bg-err/10 px-4 py-3 text-sm">
          <p className="font-mono text-xs text-err">{actionError.record.code}</p>
          <p className="mt-1 text-ink">{actionError.record.message}</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        {/* 时间线 */}
        <aside className="rounded-md border border-edge bg-panel p-4">
          <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-faint">
            执行时间线
          </h2>
          <Timeline job={job} events={detail.data?.events ?? []} />
        </aside>

        {/* 主区 */}
        <div className="min-w-0 space-y-4">
          {/* 审批门：整个产品的关键时刻 */}
          {job.status === "awaiting_review" && (
            <div className="relative overflow-hidden rounded-md border border-accent/60 bg-accent/5 p-5">
              <div
                className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent to-transparent"
                aria-hidden
              />
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex-1">
                  <h2 className="font-mono text-sm font-semibold tracking-wider text-accent">
                    审阅关口
                  </h2>
                  <p className="mt-1 text-xs text-muted">
                    {plan.data
                      ? `${plan.data.operations.length} 个操作 · ${plan.data.diffs.length} 个文件 · 静态验证${plan.data.static_validation.passed ? "通过" : `发现 ${plan.data.static_validation.error_count} 条阻塞`}`
                      : "计划载入中…"}
                    ——批准后才会应用到 VFS 并打包，原始文件永远不被修改。
                  </p>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => reject.mutate()}
                    disabled={reject.isPending || approve.isPending}
                    className="rounded-sm border border-edge px-4 py-2 font-mono text-sm text-muted transition hover:border-err hover:text-err focus-visible:outline focus-visible:outline-2 focus-visible:outline-err disabled:opacity-40"
                  >
                    拒绝
                  </button>
                  <button
                    onClick={() => approve.mutate()}
                    disabled={approve.isPending || reject.isPending}
                    className="rounded-sm border border-accent bg-accent px-6 py-2 font-mono text-sm font-bold tracking-wider text-bg transition hover:brightness-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
                  >
                    {approve.isPending ? "提交中…" : "批准并应用 ✓"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* 完成动作条 */}
          {job.status === "completed" && (
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-ok/40 bg-ok/10 px-4 py-3">
              <span className="font-mono text-sm font-semibold text-ok">
                ModPackage 已就绪
              </span>
              <span className="text-xs text-muted">
                {report.data?.probe.passed ? "运行时探针通过" : "查看报告了解探针结果"}
              </span>
              <div className="ml-auto flex gap-3">
                <a
                  href={api.packageUrl(id)}
                  className="rounded-sm border border-ok bg-ok/15 px-4 py-1.5 font-mono text-sm font-semibold text-ok transition hover:bg-ok/25"
                >
                  下载 ModPackage ↓
                </a>
                <button
                  onClick={() => {
                    if (window.confirm("回滚将作废 ModPackage 并校验游戏目录完整性，确认？")) {
                      rollback.mutate();
                    }
                  }}
                  disabled={rollback.isPending}
                  className="rounded-sm border border-edge px-4 py-1.5 font-mono text-sm text-muted transition hover:border-err hover:text-err disabled:opacity-40"
                >
                  回滚
                </button>
              </div>
            </div>
          )}

          {/* 标签页 */}
          <nav className="flex gap-1 border-b border-edge" role="tablist">
            {(
              [
                ["diff", "文件 DIFF"],
                ["plan", "操作与证据"],
                ["report", "验证报告"],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                onClick={() => setTab(key)}
                className={`px-4 py-2 font-mono text-xs tracking-wider transition ${
                  tab === key
                    ? "border-b-2 border-accent text-accent"
                    : "text-muted hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>

          {/* 内容区 */}
          {tab === "diff" &&
            (plan.data ? (
              <DiffView diffs={plan.data.diffs} />
            ) : (
              <Empty text={planReady ? "载入中…" : "计划生成后展示文件 diff"} />
            ))}

          {tab === "plan" &&
            (plan.data ? (
              <div className="space-y-4">
                <ValidationView v={plan.data.static_validation} />
                <div className="grid gap-3 md:grid-cols-2">
                  {plan.data.operations.map((op, i) => (
                    <OpCard key={i} op={op} index={i} />
                  ))}
                </div>
              </div>
            ) : (
              <Empty text={planReady ? "载入中…" : "计划生成后展示操作与证据"} />
            ))}

          {tab === "report" &&
            (report.data ? (
              <div className="space-y-6">
                <ValidationView v={report.data.static_validation} />
                <ProbeView report={report.data} />
              </div>
            ) : (
              <Empty text={reportReady ? "载入中…" : "批准并验证后生成报告"} />
            ))}
        </div>
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-dashed border-edge px-4 py-12 text-center font-mono text-xs text-faint">
      {text}
    </div>
  );
}
