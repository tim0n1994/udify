"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { Suspense, lazy, useState, useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { Timeline } from "@/components/Timeline";
import { api, queryKeys, type Job } from "@/lib/api";
import { cn } from "@/lib/cn";
import { shortHash } from "@/lib/ui";
import { AuditTreatySeal } from "./AuditTreatySeal";
import { PrismFallback } from "./PrismVisualizer.lazy";

const LazyPrism = lazy(() =>
  import("./PrismVisualizer.lazy").then((mod) => ({ default: mod.PrismVisualizerLazy })),
);

function useIsClient(): boolean {
  const [isClient, setIsClient] = useState(false);
  useEffect(() => setIsClient(true), []);
  return isClient;
}

/**
 * C-04 / C-05 证据舱：选中任务的审计链 + 时间线 + WebGL 证据场，
 * 把后端链式哈希（ORCH-JOB-04）与 job_events（OBS-01 trace）同屏演出来。
 */
export function EvidenceBay({ job, jobs }: { job: Job | null; jobs: Job[] }) {
  const isClient = useIsClient();
  const detail = useQuery({
    queryKey: queryKeys.job(job?.job_id ?? "none"),
    queryFn: () => api.getJob(job!.job_id),
    enabled: Boolean(job),
    refetchInterval: job && detailActive(job.status) ? 4_000 : false,
  });


  const events = detail.data?.events ?? [];
  const valid = detail.data ? detail.data.audit_chain_valid : null;

  return (
    <section className="dossier" aria-labelledby="evidence-heading">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-edge px-4 py-3 sm:px-5">
        <div className="mr-auto">
          <p className="dossier-index">C-04 · Evidence bay</p>
          <h2 id="evidence-heading" className="mt-1 text-sm font-semibold text-ink">
            审计链与证据场
          </h2>
        </div>
        <AuditTreatySeal valid={valid} events={events} jobId={job?.job_id ?? null} />
        {job ? (
          <Button asChild size="sm" variant="ghost">
            <Link href={`/jobs/${job.job_id}`}>
              <ExternalLink className="h-3.5 w-3.5" aria-hidden /> 完整审阅
            </Link>
          </Button>
        ) : null}
      </header>

      {job ? (
        <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(280px,360px)]">
          <div
            aria-label="WebGL 证据场画布"
            className="h-[300px] border-b border-edge sm:h-[360px] lg:border-b-0 lg:border-r"
          >
            {isClient ? (
              <Suspense fallback={<PrismFallback />}>
                <LazyPrism
                  jobs={jobs}
                  selected={{ events: events.length, valid: valid !== false }}
                />
              </Suspense>
            ) : (
              <PrismFallback />
            )}
          </div>
          <div className="p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="control-label">运行时事件流</span>
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 font-mono text-[10px]",
                  valid === false ? "text-err" : "text-ok",
                )}
              >
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
                {valid === null ? "校验中" : valid ? "链完整" : "链失配"}
              </span>
            </div>
            {events.length > 0 ? (
              <Timeline job={job} events={events.slice(-14)} />
            ) : (
              <p className="font-mono text-[11px] text-faint">该任务尚无审计事件记录。</p>
            )}
            <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-edge pt-3 font-mono text-[10px] text-faint">
              <div>
                <dt className="uppercase tracking-widest">Job</dt>
                <dd className="mt-0.5 break-all text-muted">{job.job_id}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-widest">图基线</dt>
                <dd className="mt-0.5 text-muted">
                  {shortHash(job.checkpoint.graph_checksum as string | undefined)}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      ) : (
        <p className="px-5 py-12 text-center font-mono text-xs text-faint">
          在生产矩阵中选择一条任务，展示其审计链与证据场。
        </p>
      )}
    </section>
  );
}

function detailActive(status: string): boolean {
  return ["created", "perceiving", "planning", "applying", "validating", "packaging", "compensating"].includes(status);
}
