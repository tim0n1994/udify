import type { JobStatus } from "./api";

/** 状态 → 中文标签 + 色彩语义 */
export const STATUS_META: Record<
  JobStatus,
  { label: string; tone: "active" | "gate" | "ok" | "err" | "muted" }
> = {
  created: { label: "已创建", tone: "muted" },
  perceiving: { label: "感知中", tone: "active" },
  planning: { label: "规划中", tone: "active" },
  awaiting_review: { label: "待审阅", tone: "gate" },
  applying: { label: "应用中", tone: "active" },
  validating: { label: "验证中", tone: "active" },
  packaging: { label: "打包中", tone: "active" },
  completed: { label: "已完成", tone: "ok" },
  failed: { label: "失败", tone: "err" },
  compensating: { label: "回滚中", tone: "active" },
  rolled_back: { label: "已回滚", tone: "muted" },
  rejected: { label: "已拒绝", tone: "muted" },
};

export const ACTIVE_STATUSES: JobStatus[] = [
  "created",
  "perceiving",
  "planning",
  "applying",
  "validating",
  "packaging",
  "compensating",
];

/** 连续风险分 → R0-R4 档位 */
export function riskLevel(risk: number): 0 | 1 | 2 | 3 | 4 {
  if (risk < 0.15) return 0;
  if (risk < 0.35) return 1;
  if (risk < 0.55) return 2;
  if (risk < 0.75) return 3;
  return 4;
}

export const RISK_COLORS = [
  "text-r0 border-r0/40 bg-r0/10",
  "text-r1 border-r1/40 bg-r1/10",
  "text-r2 border-r2/40 bg-r2/10",
  "text-r3 border-r3/40 bg-r3/10",
  "text-r4 border-r4/40 bg-r4/10",
] as const;

export function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function shortHash(hash: string | null | undefined): string {
  return hash ? `${hash.slice(0, 12)}…` : "—";
}
