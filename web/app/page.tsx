"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fmtTime } from "@/lib/ui";
import { StatusBadge } from "@/components/StatusBadge";

export default function ConsolePage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [gameRoot, setGameRoot] = useState("");
  const [intent, setIntent] = useState("");
  const [formError, setFormError] = useState<ApiError | null>(null);

  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: 2000,
  });

  const create = useMutation({
    mutationFn: () => api.createJob(gameRoot.trim(), intent.trim()),
    onSuccess: (job) => {
      setFormError(null);
      setIntent("");
      qc.invalidateQueries({ queryKey: ["jobs"] });
      router.push(`/jobs/${job.job_id}`);
    },
    onError: (e) => setFormError(e instanceof ApiError ? e : null),
  });

  return (
    <div className="space-y-10">
      {/* 新任务：整个产品的第一入口 */}
      <section className="relative overflow-hidden rounded-md border border-edge bg-panel p-6">
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent"
          aria-hidden
        />
        <h1 className="mb-1 font-mono text-sm uppercase tracking-[0.2em] text-accent">
          新建 Mod 任务
        </h1>
        <p className="mb-5 text-sm text-muted">
          指向一个 miu2d 游戏目录，用一句话说出你想要的改动。系统会生成带证据的修改计划，等你审阅批准。
        </p>
        <form
          className="grid gap-4 md:grid-cols-[1fr_1.2fr_auto]"
          onSubmit={(e) => {
            e.preventDefault();
            if (gameRoot.trim() && intent.trim()) create.mutate();
          }}
        >
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-faint">
              游戏目录 game_root
            </span>
            <input
              value={gameRoot}
              onChange={(e) => setGameRoot(e.target.value)}
              placeholder="/path/to/miu2d-game"
              className="w-full rounded-sm border border-edge bg-bg px-3 py-2 font-mono text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-faint">
              修改意图 intent
            </span>
            <input
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder="让第一个 Boss 更难，但不要单纯翻倍血量"
              className="w-full rounded-sm border border-edge bg-bg px-3 py-2 text-sm text-ink placeholder:text-faint focus:border-accent focus:outline-none"
              required
            />
          </label>
          <button
            type="submit"
            disabled={create.isPending || !gameRoot.trim() || !intent.trim()}
            className="self-end rounded-sm border border-accent bg-accent/15 px-5 py-2 font-mono text-sm font-semibold tracking-wider text-accent transition hover:bg-accent/25 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {create.isPending ? "创建中…" : "生成计划 →"}
          </button>
        </form>
        {formError && (
          <div className="mt-4 rounded-sm border border-err/40 bg-err/10 px-4 py-3 text-sm">
            <p className="font-mono text-xs text-err">{formError.record.code}</p>
            <p className="mt-1 text-ink">{formError.record.message}</p>
            {formError.record.suggested_action && (
              <p className="mt-1 text-xs text-muted">→ {formError.record.suggested_action}</p>
            )}
          </div>
        )}
      </section>

      {/* 任务台账 */}
      <section>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
            任务台账
          </h2>
          <span className="font-mono text-[10px] text-faint">
            {jobs.data ? `${jobs.data.length} 条` : "…"}
          </span>
        </div>
        {jobs.isError && (
          <div className="rounded-md border border-err/40 bg-err/10 px-4 py-6 text-center text-sm text-muted">
            后端离线 —— 在项目目录运行{" "}
            <code className="rounded bg-bg px-1.5 py-0.5 font-mono text-accent">
              udify serve
            </code>{" "}
            后自动恢复
          </div>
        )}
        {jobs.data && jobs.data.length === 0 && (
          <div className="rounded-md border border-dashed border-edge px-4 py-10 text-center text-sm text-faint">
            还没有任务。上面提交第一个意图。
          </div>
        )}
        <ul className="divide-y divide-edge overflow-hidden rounded-md border border-edge">
          {jobs.data?.map((job) => (
            <li key={job.job_id}>
              <button
                onClick={() => router.push(`/jobs/${job.job_id}`)}
                className="flex w-full items-center gap-4 bg-panel px-4 py-3 text-left transition hover:bg-panel-2 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
              >
                <span className="font-mono text-xs text-faint">{job.job_id}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">
                  {job.intent}
                </span>
                <span className="hidden font-mono text-[11px] text-faint md:block">
                  {fmtTime(job.created_at)}
                </span>
                <StatusBadge status={job.status} />
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
