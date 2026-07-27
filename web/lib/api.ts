/**
 * Udify API client（手写薄封装，ADR-v3-009：端点少，不上代码生成）。
 * 信封 {success, data, error, meta}；错误抛 ApiError（携带 ErrorRecord）。
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_UDIFY_API ?? "http://127.0.0.1:8765";

export interface ErrorRecord {
  code: string;
  message: string;
  owner_module: string;
  retryable: boolean;
  suggested_action: string;
}

export class ApiError extends Error {
  record: ErrorRecord;
  status: number;

  constructor(record: ErrorRecord, status: number) {
    super(record.message);
    this.record = record;
    this.status = status;
  }
}

interface Envelope<T> {
  success: boolean;
  data: T;
  error: ErrorRecord | null;
  meta: Record<string, unknown> | null;
}

export type JobStatus =
  | "created"
  | "perceiving"
  | "planning"
  | "awaiting_review"
  | "applying"
  | "validating"
  | "packaging"
  | "completed"
  | "failed"
  | "compensating"
  | "rolled_back"
  | "rejected";

export interface Job {
  job_id: string;
  game_root: string;
  intent: string;
  status: JobStatus;
  created_at: number;
  updated_at: number;
  artifacts_dir: string;
  error: ErrorRecord | null;
  checkpoint: Record<string, unknown>;
}

export interface JobEvent {
  job_id: string;
  seq: number;
  ts: number;
  stage: string;
  event: string;
  payload: Record<string, unknown>;
  record_hash: string;
}

export interface JobDetail {
  job: Job;
  events: JobEvent[];
  audit_chain_valid: boolean;
}

export interface SourceSpan {
  file_path: string;
  line_start: number | null;
  line_end: number | null;
}

export interface PatchOp {
  op_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  execution_mode?: string;
  source_span?: SourceSpan;
  risk?: number;
  planning_reason?: string;
}

export interface DiffChange {
  type: "add" | "remove";
  line: string;
}

export interface FileDiff {
  path: string;
  status: "modified" | "new" | "deleted";
  original: string | null;
  current: string | null;
  diff?: DiffChange[];
}

export interface ValidationFinding {
  check: string;
  severity: string;
  message: string;
  target_id: string;
  evidence: Record<string, unknown>;
}

export interface StaticValidation {
  passed: boolean;
  blocking_errors: ValidationFinding[];
  warnings: ValidationFinding[];
  confidence: number;
  recommended_action: string;
  error_count: number;
  warning_count: number;
}

export interface Plan {
  intent: string;
  graph_checksum: string;
  actions: { schema: string; target: string; params: Record<string, unknown>; reason: string }[];
  operations: PatchOp[];
  diffs: FileDiff[];
  op_errors: string[];
  static_validation: StaticValidation;
}

export interface ProbeResult {
  probe_id: string;
  passed: boolean;
  kind: string;
  observed: Record<string, unknown>;
  console_errors: string[];
  evidence: string;
}

export interface Report {
  static_validation: StaticValidation;
  probe: {
    passed: boolean;
    game_started: boolean;
    state_readable: boolean;
    console_error_count: number;
    probe_count: number;
    results: ProbeResult[];
  };
  graph_checksum_before: string | null;
  graph_checksum_applied_on: string;
}

export interface ModsData {
  mods: {
    job_id: string;
    intent: string;
    package: string | null;
    operations: number;
    created_at: number;
  }[];
  conflicts: { job_a: string; job_b: string; shared_targets: string[] }[];
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      {
        code: "API_CONN_REFUSED",
        message: "无法连接后端，请先运行 `udify serve`",
        owner_module: "web",
        retryable: true,
        suggested_action: "在项目目录执行 udify serve（默认 127.0.0.1:8765）",
      },
      0,
    );
  }
  const body = (await res.json()) as Envelope<T>;
  if (!body.success || body.error) {
    throw new ApiError(
      body.error ?? {
        code: "API_UNKNOWN_ERROR",
        message: `HTTP ${res.status}`,
        owner_module: "web",
        retryable: false,
        suggested_action: "",
      },
      res.status,
    );
  }
  return body.data;
}

export const api = {
  healthz: () =>
    call<{ version: string; engines: Record<string, boolean> }>("/api/v0/healthz"),
  createJob: (game_root: string, intent: string) =>
    call<Job>("/api/v0/jobs", {
      method: "POST",
      body: JSON.stringify({ game_root, intent }),
    }),
  listJobs: () => call<Job[]>("/api/v0/jobs"),
  getJob: (id: string) => call<JobDetail>(`/api/v0/jobs/${id}`),
  getPlan: (id: string) => call<Plan>(`/api/v0/jobs/${id}/plan`),
  approve: (id: string) => call<Job>(`/api/v0/jobs/${id}/approve`, { method: "POST" }),
  reject: (id: string, reason: string) =>
    call<Job>(`/api/v0/jobs/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  getReport: (id: string) => call<Report>(`/api/v0/jobs/${id}/report`),
  rollback: (id: string) => call<Job>(`/api/v0/jobs/${id}/rollback`, { method: "POST" }),
  listMods: (game_root: string) =>
    call<ModsData>(`/api/v0/mods?game_root=${encodeURIComponent(game_root)}`),
  packageUrl: (id: string) => `${API_BASE}/api/v0/jobs/${id}/package`,
};
