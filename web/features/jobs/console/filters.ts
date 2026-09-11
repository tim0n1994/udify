import { ACTIVE_STATUSES, type Job } from "@/lib/api";

export type JobFilter = "all" | "awaiting_clarification" | "awaiting_review" | "active" | "completed" | "failed";

export function filterJobs(jobs: Job[], search: string, filter: JobFilter): Job[] {
  const needle = search.trim().toLocaleLowerCase("zh-CN");
  return jobs.filter((job) => {
    const matchesSearch =
      needle.length === 0 ||
      job.intent.toLocaleLowerCase("zh-CN").includes(needle) ||
      job.game_root.toLocaleLowerCase("zh-CN").includes(needle) ||
      job.job_id.toLocaleLowerCase("zh-CN").includes(needle);
    const matchesFilter =
      filter === "all" ||
      (filter === "active" && ACTIVE_STATUSES.includes(job.status)) ||
      (filter === "failed" && job.status === "failed") ||
      job.status === filter;
    return matchesSearch && matchesFilter;
  });
}

/** Keep selection inside the visible result set; otherwise choose its first row. */
export function selectVisibleJob(jobs: Job[], selectedId: string | null): Job | null {
  return jobs.find((job) => job.job_id === selectedId) ?? jobs[0] ?? null;
}
