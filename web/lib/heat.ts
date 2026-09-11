import type { Job, JobStatus } from "@/lib/api";

export type HeatCellTone = "gate" | "active" | "err" | "ok" | "idle";

export interface HeatCell {
  status: JobStatus;
  label: string;
  jobs: Job[];
  tone: HeatCellTone;
}

const HEAT_ORDER: readonly [JobStatus, string, HeatCellTone][] = [
  ["awaiting_review", "待审阅", "gate"],
  ["awaiting_clarification", "待确认目标", "gate"],
  ["perceiving", "感知", "active"],
  ["planning", "规划", "active"],
  ["applying", "应用", "active"],
  ["validating", "验证", "active"],
  ["packaging", "打包", "active"],
  ["compensating", "回滚中", "active"],
  ["completed", "已完成", "ok"],
  ["failed", "失败", "err"],
  ["rolled_back", "已回滚", "idle"],
  ["rejected", "已拒绝", "idle"],
];

/** Ops × 风险/状态热力矩阵：把 JobStore 快照聚合为驾驶舱仪表盘。 */
export function buildHeatCells(jobs: Job[]): HeatCell[] {
  return HEAT_ORDER.map(([status, label, tone]) => ({
    status,
    label,
    tone,
    jobs: jobs.filter((job) => job.status === status),
  }));
}

export function dominantCell(cells: HeatCell[]): HeatCell | null {
  return [...cells].sort((a, b) => b.jobs.length - a.jobs.length)[0] ?? null;
}
