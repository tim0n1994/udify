"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ProbeView } from "@/components/ProbeView";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { ValidationView } from "@/components/ValidationView";
import { ApprovalChecklist } from "@/features/jobs/review/ApprovalChecklist";
import { DiffPane } from "@/features/jobs/review/DiffPane";
import { FileRail } from "@/features/jobs/review/FileRail";
import { JobActions } from "@/features/jobs/review/JobActions";
import { OperationTable } from "@/features/jobs/review/OperationTable";
import { ReviewTabs } from "@/features/jobs/review/ReviewTabs";
import {
  api,
  ApiError,
  jobPollInterval,
  queryKeys,
  type PatchOp,
} from "@/lib/api";
import { useConfig, type JobTab } from "@/lib/config";
import { fmtTime, shortHash } from "@/lib/ui";
import { useSound } from "@/lib/sound";
import { AuditTreatySeal } from "@/features/jobs/cockpit/AuditTreatySeal";

export default function JobPage() {
  return (
    <Suspense fallback={<JobPageSkeleton />}>
      <JobPageContent />
    </Suspense>
  );
}

function JobPageContent() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const sound = useSound();
  const { config } = useConfig();
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedOp, setSelectedOp] = useState<number | null>(null);
  const [actionError, setActionError] = useState<ApiError | null>(null);

  const requestedTab = searchParams.get("tab");
  const tab: JobTab = isJobTab(requestedTab) ? requestedTab : config.defaultJobTab;
  useEffect(() => {
    if (!isJobTab(requestedTab)) {
      const next = new URLSearchParams(searchParams.toString());
      next.set("tab", config.defaultJobTab);
      router.replace(`?${next.toString()}`, { scroll: false });
    }
  }, [config.defaultJobTab, requestedTab, router, searchParams]);

  const detail = useQuery({
    queryKey: queryKeys.job(id),
    queryFn: () => api.getJob(id),
    refetchInterval: (query) =>
      jobPollInterval(
        query.state.data?.job.status,
        config,
        typeof document === "undefined" || document.visibilityState === "visible",
      ),
  });
  const job = detail.data?.job;
  const planReady = Boolean(
    job &&
      ([
        "awaiting_review",
        "applying",
        "validating",
        "packaging",
        "completed",
        "rolled_back",
        "rejected",
      ].includes(job.status) || job.checkpoint.operations),
  );
  const reportReady = Boolean(job && ["completed", "rolled_back", "failed"].includes(job.status));
  const plan = useQuery({
    queryKey: queryKeys.plan(id),
    queryFn: () => api.getPlan(id),
    enabled: planReady,
    retry: false,
  });
  const report = useQuery({
    queryKey: queryKeys.report(id),
    queryFn: () => api.getReport(id),
    enabled: reportReady,
    retry: false,
  });

  useEffect(() => {
    if (!selectedFile && plan.data?.diffs[0]) setSelectedFile(plan.data.diffs[0].path);
  }, [plan.data, selectedFile]);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.job(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.report(id) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs }),
    ]);
  };
  const mutationOptions = {
    onSuccess: async () => {
      setActionError(null);
      await invalidate();
    },
    onError: (error: unknown) => {
      setActionError(error instanceof ApiError ? error : null);
      sound.play("fail");
    },
  };
  const approve = useMutation({
    mutationFn: () => api.approve(id),
    ...mutationOptions,
    onSuccess: async () => {
      sound.play("approve");
      await invalidate();
      setActionError(null);
    },
  });
  const reject = useMutation({
    mutationFn: (reason: string) => api.reject(id, reason),
    onError: mutationOptions.onError,
    onSuccess: async () => {
      sound.play("reject");
      await invalidate();
      setActionError(null);
    },
  });
  const rollback = useMutation({ mutationFn: () => api.rollback(id), ...mutationOptions });

  const selectedDiff =
    plan.data?.diffs.find((diff) => diff.path === selectedFile) ?? plan.data?.diffs[0] ?? null;
  const anchor = selectedOp === null ? undefined : plan.data?.operations[selectedOp]?.source_span;
  const highestRisk = useMemo(
    () => Math.max(0, ...(plan.data?.operations.map((operation) => operation.risk ?? 0) ?? [])),
    [plan.data],
  );

  if (detail.isLoading) return <JobPageSkeleton />;
  if (detail.isError || !job) {
    const error = detail.error;
    return (
      <div className="mx-auto max-w-3xl">
        <ErrorState
          title={error instanceof ApiError ? error.record.code : "JOB_LOAD_FAILED"}
          message={error instanceof ApiError ? error.record.message : "无法读取任务"}
          action={error instanceof ApiError ? error.record.suggested_action : undefined}
          onRetry={() => void detail.refetch()}
        />
      </div>
    );
  }

  const changePanel = plan.data ? (
    <div className="space-y-3">
      <div className="surface grid min-h-[470px] overflow-hidden xl:grid-cols-[220px_minmax(0,1fr)_300px]">
        <FileRail
          diffs={plan.data.diffs}
          operations={plan.data.operations}
          selectedPath={selectedDiff?.path ?? null}
          onSelect={(path) => {
            setSelectedFile(path);
            setSelectedOp(null);
          }}
        />
        <DiffPane diff={selectedDiff} anchor={anchor} />
        <aside className="grid gap-0 border-t border-edge xl:border-l xl:border-t-0">
          <section className="border-b border-edge p-4">
            <h2 className="mb-3 text-sm font-semibold text-ink">阶段时间线</h2>
            <Timeline job={job} events={detail.data?.events ?? []} />
          </section>
          <ApprovalChecklist
            plan={plan.data}
            auditValid={detail.data?.audit_chain_valid ?? false}
          />
        </aside>
      </div>
      <OperationTable
        operations={plan.data.operations}
        selectedIndex={selectedOp}
        onSelect={(operation: PatchOp, index) => {
          setSelectedOp(index);
          const path = operation.source_span?.file_path;
          if (path && plan.data.diffs.some((diff) => diff.path === path)) setSelectedFile(path);
        }}
      />
    </div>
  ) : plan.isError ? (
    <ErrorState
      title={plan.error instanceof ApiError ? plan.error.record.code : "PLAN_LOAD_FAILED"}
      message={plan.error instanceof ApiError ? plan.error.record.message : "无法读取修改计划"}
      onRetry={() => void plan.refetch()}
    />
  ) : (
    <PendingPanel text={planReady ? "正在读取计划…" : "计划生成后将在此展示 diff 与 SourceSpan 证据"} />
  );

  const riskPanel = plan.data ? (
    <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="min-w-0 space-y-4">
        <ValidationView v={plan.data.static_validation} />
        <OperationTable
          operations={plan.data.operations}
          selectedIndex={selectedOp}
          onSelect={(operation, index) => {
            setSelectedOp(index);
            if (operation.source_span?.file_path) setSelectedFile(operation.source_span.file_path);
          }}
        />
      </div>
      <div className="surface min-w-0 h-fit">
        <ApprovalChecklist plan={plan.data} auditValid={detail.data?.audit_chain_valid ?? false} />
        <JobActions
          job={job}
          plan={plan.data}
          highestRisk={highestRisk}
          approvePending={approve.isPending}
          rejectPending={reject.isPending}
          rollbackPending={rollback.isPending}
          onApprove={() => approve.mutate()}
          onReject={(reason) => reject.mutate(reason)}
          onRollback={() => rollback.mutate()}
        />
      </div>
    </div>
  ) : (
    <PendingPanel text="计划就绪后可进行风险审阅" />
  );

  const reportPanel = report.data ? (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(340px,0.75fr)]">
      <ValidationView v={report.data.static_validation} />
      <ProbeView report={report.data} />
    </div>
  ) : report.isError ? (
    <ErrorState
      title={report.error instanceof ApiError ? report.error.record.code : "REPORT_LOAD_FAILED"}
      message={report.error instanceof ApiError ? report.error.record.message : "无法读取验证报告"}
      action={report.error instanceof ApiError ? report.error.record.suggested_action : undefined}
      onRetry={() => void report.refetch()}
    />
  ) : (
    <PendingPanel text={reportReady ? "正在读取验证报告…" : "批准并完成验证后生成报告"} />
  );

  return (
    <div className="mx-auto max-w-[1600px] space-y-4">
      <header className="space-y-3">
        <div className="flex items-center gap-2 font-mono text-[11px] text-faint">
          <Link href="/" className="inline-flex items-center gap-1 hover:text-accent">
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> 任务
          </Link>
          <span>/</span><span>{job.job_id}</span>
        </div>
        <div className="flex flex-wrap items-start gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold leading-tight text-ink sm:text-2xl">{job.intent}</h1>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
              <StatusBadge status={job.status} />
              <AuditTreatySeal
                valid={detail.data?.audit_chain_valid ?? null}
                events={detail.data?.events ?? []}
                jobId={job.job_id}
              />
              <span className="font-mono">创建 {fmtTime(job.created_at)}</span>
              <span className="font-mono">图基线 {shortHash(job.checkpoint.graph_checksum as string | undefined)}</span>
              <span className="max-w-lg truncate font-mono" title={job.game_root}>{job.game_root}</span>
            </div>
          </div>
          {job.status === "completed" ? (
            <Button asChild variant="primary">
              <a href={api.packageUrl(id)}><Download className="h-4 w-4" aria-hidden /> 下载 ModPackage</a>
            </Button>
          ) : null}
        </div>
      </header>

      {!detail.data?.audit_chain_valid ? (
        <div role="alert" className="flex gap-2 border border-err/60 bg-err/10 p-3 text-sm text-err">
          <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden /> 审计链校验失败，不应批准。
        </div>
      ) : null}
      {job.error ? (
        <ErrorState title={job.error.code} message={job.error.message} action={job.error.suggested_action} />
      ) : null}
      {actionError ? (
        <ErrorState
          title={actionError.record.code}
          message={actionError.record.message}
          action={actionError.record.suggested_action}
        />
      ) : null}

      <ReviewTabs
        value={tab}
        onValueChange={(next) => {
          const params = new URLSearchParams(searchParams.toString());
          params.set("tab", next);
          router.replace(`?${params.toString()}`, { scroll: false });
        }}
        changes={changePanel}
        risk={riskPanel}
        report={reportPanel}
      />
    </div>
  );
}

function isJobTab(value: string | null): value is JobTab {
  return value === "changes" || value === "risk" || value === "report";
}

function PendingPanel({ text }: { text: string }) {
  return <div className="surface p-12 text-center font-mono text-xs text-faint">{text}</div>;
}

function JobPageSkeleton() {
  return (
    <div className="mx-auto max-w-[1600px] space-y-4" aria-label="正在加载任务">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-[520px] w-full" />
    </div>
  );
}
