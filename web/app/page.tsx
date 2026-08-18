"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { CommandPalette } from "@/features/jobs/cockpit/CommandPalette";
import { EvidenceBay } from "@/features/jobs/cockpit/EvidenceBay";
import { MissionStrip } from "@/features/jobs/cockpit/MissionStrip";
import { OpsMatrix } from "@/features/jobs/cockpit/OpsMatrix";
import { CreateJobForm } from "@/features/jobs/console/CreateJobForm";
import { JobFilters } from "@/features/jobs/console/JobFilters";
import { JobInspector } from "@/features/jobs/console/JobInspector";
import { JobTable } from "@/features/jobs/console/JobTable";
import {
  filterJobs,
  selectVisibleJob,
  type JobFilter,
} from "@/features/jobs/console/filters";
import { api, ApiError, jobsPollInterval, queryKeys } from "@/lib/api";
import { useConfig } from "@/lib/config";
import { useSound } from "@/lib/sound";

export default function ConsolePage() {
  return (
    <Suspense fallback={null}>
      <ConsolePageContent />
    </Suspense>
  );
}

function ConsolePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const { config } = useConfig();
  const sound = useSound();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<JobFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [formError, setFormError] = useState<ApiError | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const status = searchParams.get("status");
    if (status && ["all", "awaiting_review", "active", "completed", "failed"].includes(status)) {
      setFilter(status as JobFilter);
    }
  }, [searchParams]);

  const jobs = useQuery({
    queryKey: queryKeys.jobs,
    queryFn: api.listJobs,
    refetchInterval: (query) =>
      jobsPollInterval(
        query.state.data,
        config,
        typeof document === "undefined" || document.visibilityState === "visible",
      ),
  });

  const create = useMutation({
    mutationFn: ({ gameRoot, intent }: { gameRoot: string; intent: string }) =>
      api.createJob(gameRoot, intent),
    onSuccess: async (job) => {
      setFormError(null);
      sound.play("create");
      await queryClient.invalidateQueries({ queryKey: queryKeys.jobs });
      router.push(`/jobs/${job.job_id}`);
    },
    onError: (error) => setFormError(error instanceof ApiError ? error : null),
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filtered = useMemo(
    () => filterJobs(jobs.data ?? [], search, filter),
    [filter, jobs.data, search],
  );
  const selected = selectVisibleJob(filtered, selectedId);

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <CommandPalette open={paletteOpen} jobs={jobs.data} onClose={() => setPaletteOpen(false)} />

      <MissionStrip jobs={jobs.data} onOpenCommand={() => setPaletteOpen(true)} />

      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-edge pb-5">
        <div>
          <p className="dossier-index">Evidence operations · C-00</p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            证据驾驶舱
          </h1>
          <div className="dossier-rule" aria-hidden />
          <p className="mt-3 max-w-xl text-sm text-muted">
            意图一经提交，感知→规划→证据→审阅→验证→打包全程可追溯；审计链失配会在 1 秒内变红。
          </p>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-faint">
          Udify · local · single-user
        </p>
      </header>

      <section aria-labelledby="create-heading" className="dossier p-4 sm:p-5">
        <p className="dossier-index">C-02 · Intent intake</p>
        <h2 id="create-heading" className="sr-only">
          创建任务
        </h2>
        <div className="mt-3">
          <CreateJobForm
            pending={create.isPending}
            apiError={formError}
            onSubmit={async (input) => {
              await create.mutateAsync(input);
            }}
          />
        </div>
      </section>

      <section aria-labelledby="matrix-heading" className="space-y-3">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="dossier-index">C-03 · Ops heat matrix</p>
            <h2 id="matrix-heading" className="mt-1 text-sm font-semibold text-ink">
              生产矩阵
            </h2>
          </div>
          <p className="font-mono text-[10px] text-faint">hover / Enter 深链到任务</p>
        </div>
        <OpsMatrix jobs={jobs.data} />
      </section>

      <section className="surface overflow-hidden" aria-labelledby="recent-jobs-title">
        <div className="flex flex-wrap items-center gap-3 border-b border-edge px-4 py-3 sm:px-5">
          <div className="mr-auto">
            <p className="dossier-index">C-03b · Feed</p>
            <h2 id="recent-jobs-title" className="text-sm font-semibold text-ink">
              任务流
            </h2>
            <p className="mt-0.5 font-mono text-[10px] text-faint">
              {jobs.data ? `${jobs.data.length} 条后端记录` : "正在读取本地 JobStore"}
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => void jobs.refetch()}
            disabled={jobs.isFetching}
            aria-label="刷新任务"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${jobs.isFetching ? "animate-spin" : ""}`} aria-hidden />
            刷新
          </Button>
        </div>

        <JobFilters
          search={search}
          filter={filter}
          onSearch={setSearch}
          onFilter={setFilter}
          onClear={() => {
            setSearch("");
            setFilter("all");
          }}
        />

        {jobs.isLoading ? (
          <div className="space-y-px p-1" aria-label="正在加载任务">
            {Array.from({ length: 5 }, (_, index) => (
              <Skeleton key={index} className="h-12" />
            ))}
          </div>
        ) : null}

        {jobs.isError ? (
          <div className="p-4">
            <ErrorState
              title={jobs.error instanceof ApiError ? jobs.error.record.code : "API_OFFLINE"}
              message={
                jobs.error instanceof ApiError ? jobs.error.record.message : "无法加载任务"
              }
              action={jobs.error instanceof ApiError ? jobs.error.record.suggested_action : undefined}
              onRetry={() => void jobs.refetch()}
            />
          </div>
        ) : null}

        {jobs.data ? (
          <div
            className={
              config.features.showJobInspector
                ? "grid xl:grid-cols-[minmax(0,1fr)_320px]"
                : "block"
            }
          >
            <JobTable
              jobs={filtered}
              selectedId={selected?.job_id ?? null}
              hasFilters={Boolean(search.trim()) || filter !== "all"}
              onSelect={(job) => setSelectedId(job.job_id)}
              onOpen={(job) => router.push(`/jobs/${job.job_id}`)}
            />
            {config.features.showJobInspector ? (
              <JobInspector job={selected} onOpen={() => selected && router.push(`/jobs/${selected.job_id}`)} />
            ) : null}
          </div>
        ) : null}
      </section>

      <EvidenceBay job={selected} jobs={jobs.data ?? []} />
    </div>
  );
}
