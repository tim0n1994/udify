import { BUILD_CONFIG } from "@/lib/config/build";
import { z } from "zod";
import {
  envelopeSchema,
  errorRecordSchema,
  healthSchema,
  jobDetailSchema,
  jobSchema,
  modsDataSchema,
  planSchema,
  reportSchema,
} from "./schema";
import type { ErrorRecord } from "./types";

export class ApiError extends Error {
  constructor(
    public readonly record: ErrorRecord,
    public readonly status: number,
  ) {
    super(record.message);
    this.name = "ApiError";
  }
}

function localError(
  code: string,
  message: string,
  suggestedAction: string,
  retryable = true,
): ErrorRecord {
  return {
    code,
    message,
    owner_module: "web.api",
    retryable,
    suggested_action: suggestedAction,
  };
}

export async function call<T extends z.ZodType>(
  path: string,
  schema: T,
  init?: RequestInit,
  apiBase = BUILD_CONFIG.config.apiBase,
): Promise<z.infer<T>> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(
      localError(
        "API_CONN_REFUSED",
        "无法连接后端，请先运行 `udify serve`",
        "在项目目录执行 udify serve（默认 127.0.0.1:8765）",
      ),
      0,
    );
  }

  let raw: unknown;
  try {
    raw = await response.json();
  } catch {
    throw new ApiError(
      localError(
        "API_RESPONSE_INVALID",
        "后端返回了非 JSON 响应",
        "查看 udify serve 日志并重试",
      ),
      response.status,
    );
  }

  const decoded = envelopeSchema.safeParse(raw);
  if (!decoded.success) {
    throw new ApiError(
      localError(
        "API_RESPONSE_INVALID",
        `API 响应不符合 v0 契约：${decoded.error.issues[0]?.message ?? "unknown"}`,
        "检查前后端版本是否匹配",
        false,
      ),
      response.status,
    );
  }

  const envelope = decoded.data;
  if (!response.ok || !envelope.success || envelope.error) {
    const record = errorRecordSchema.safeParse(envelope.error);
    throw new ApiError(
      record.success
        ? record.data
        : localError(
            "API_UNKNOWN_ERROR",
            `HTTP ${response.status}`,
            "查看后端日志后重试",
            response.status >= 500,
          ),
      response.status,
    );
  }
  if (envelope.data === null) {
    throw new ApiError(
      localError("API_RESPONSE_INVALID", "成功信封缺少 data", "检查 API 契约", false),
      response.status,
    );
  }
  const data = schema.safeParse(envelope.data);
  if (!data.success) {
    throw new ApiError(
      localError(
        "API_RESPONSE_INVALID",
        `API data 不符合 v0 契约：${data.error.issues[0]?.message ?? "unknown"}`,
        "检查前后端版本是否匹配",
        false,
      ),
      response.status,
    );
  }
  return data.data;
}

export const api = {
  healthz: () => call("/api/v0/healthz", healthSchema),
  createJob: (gameRoot: string, intent: string) =>
    call("/api/v0/jobs", jobSchema, {
      method: "POST",
      body: JSON.stringify({ game_root: gameRoot, intent }),
    }),
  listJobs: () => call("/api/v0/jobs", z.array(jobSchema)),
  getJob: (id: string) => call(`/api/v0/jobs/${id}`, jobDetailSchema),
  getPlan: (id: string) => call(`/api/v0/jobs/${id}/plan`, planSchema),
  clarifyJob: (id: string, targetIds: string[]) =>
    call(`/api/v0/jobs/${id}/clarify`, jobSchema, {
      method: "POST", body: JSON.stringify({ target_ids: targetIds }),
    }),
  approve: (id: string) => call(`/api/v0/jobs/${id}/approve`, jobSchema, { method: "POST" }),
  reject: (id: string, reason: string) =>
    call(`/api/v0/jobs/${id}/reject`, jobSchema, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  getReport: (id: string) => call(`/api/v0/jobs/${id}/report`, reportSchema),
  rollback: (id: string) => call(`/api/v0/jobs/${id}/rollback`, jobSchema, { method: "POST" }),
  listMods: (gameRoot: string) =>
    call(`/api/v0/mods?game_root=${encodeURIComponent(gameRoot)}`, modsDataSchema),
  packageUrl: (id: string) => `${BUILD_CONFIG.config.apiBase}/api/v0/jobs/${id}/package`,
};
