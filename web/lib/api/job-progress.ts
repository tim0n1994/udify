/**
 * iter4 M4 PR3 — 进度事件类型与 Zod schema（与 Python ProgressEvent 一一对应）。
 *
 * SSE 端点 GET /api/v0/jobs/{id}/events 推送两类事件：
 * - event: progress —— ProgressEvent（stage/detail/pct/current/total/seq）
 * - event: done      —— 任务终态通知（status: completed|failed|...）
 * - 心跳为 SSE comment（`: ping`），不触发 onmessage。
 */
import { z } from "zod";
import { jobStatusSchema } from "./schema";

export const jobDoneSchema = z.object({
  job_id: z.string(), status: jobStatusSchema, seq: z.number().int().min(0),
});

export const progressStageSchema = z.enum([
  "perceiving",
  "planning",
  "applying",
  "validating",
  "packaging",
]);

export const progressEventSchema = z.object({
  job_id: z.string(),
  stage: progressStageSchema,
  detail: z.string().default(""),
  pct: z.number().min(0).max(100).default(0),
  current: z.number().int().min(0).default(0),
  total: z.number().int().min(0).default(0),
  timestamp: z.string(),
  seq: z.number().int().min(0),
});

export const progressDoneSchema = z.object({
  job_id: z.string(),
  status: z.string(),
});

export type ProgressStage = z.infer<typeof progressStageSchema>;
export type ProgressEvent_ = z.infer<typeof progressEventSchema>;
export type ProgressDone = z.infer<typeof progressDoneSchema>;

/** SSE 事件名（与后端 job_events.py 的 event= 参数一致）。 */
export const SSE_EVENT_PROGRESS = "progress";
export const SSE_EVENT_DONE = "done";
export const SSE_EVENT_ERROR = "error";
