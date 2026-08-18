import type { PublicConfig } from "@/lib/config/schema";
import type { Job, JobStatus } from "./types";

export const queryKeys = {
  health: ["healthz"] as const,
  jobs: ["jobs"] as const,
  job: (id: string) => ["job", id] as const,
  plan: (id: string) => ["plan", id] as const,
  report: (id: string) => ["report", id] as const,
};

export const ACTIVE_STATUSES: readonly JobStatus[] = [
  "created",
  "perceiving",
  "planning",
  "applying",
  "validating",
  "packaging",
  "compensating",
];

export function jobPollInterval(
  status: JobStatus | undefined,
  config: PublicConfig,
  visible = true,
): number | false {
  if (!visible || !status || !ACTIVE_STATUSES.includes(status)) return false;
  return config.polling.activeMs;
}

export function jobsPollInterval(
  jobs: Job[] | undefined,
  config: PublicConfig,
  visible = true,
): number | false {
  if (!visible) return false;
  return jobs?.some((job) => ACTIVE_STATUSES.includes(job.status))
    ? config.polling.activeMs
    : config.polling.idleMs;
}
