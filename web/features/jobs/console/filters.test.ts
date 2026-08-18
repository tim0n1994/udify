import { DEFAULT_PUBLIC_CONFIG } from "@/config/defaults";
import { jobsPollInterval, jobPollInterval } from "@/lib/api";
import { jobsFixture } from "@/test/fixtures";
import { filterJobs, selectVisibleJob } from "./filters";

describe("job filtering and polling", () => {
  it("searches intent, path and id and groups terminal statuses", () => {
    expect(filterJobs(jobsFixture, "NPC", "all")).toHaveLength(1);
    expect(filterJobs(jobsFixture, "/games/miu2d", "failed")[0]?.status).toBe("failed");
    expect(filterJobs(jobsFixture, "job-rolled", "all")[0]?.status).toBe("rolled_back");
  });

  it("polls only active detail states and pauses when hidden", () => {
    expect(jobPollInterval("planning", DEFAULT_PUBLIC_CONFIG)).toBe(1_000);
    expect(jobPollInterval("awaiting_review", DEFAULT_PUBLIC_CONFIG)).toBe(false);
    expect(jobPollInterval("planning", DEFAULT_PUBLIC_CONFIG, false)).toBe(false);
    expect(jobsPollInterval(jobsFixture, DEFAULT_PUBLIC_CONFIG)).toBe(1_000);
    expect(jobsPollInterval([], DEFAULT_PUBLIC_CONFIG)).toBe(5_000);
  });

  it("drops a selected job when filters remove it from the visible rows", () => {
    const selectedId = jobsFixture[0]?.job_id ?? null;
    const visible = filterJobs(jobsFixture, "job-rolled", "all");

    expect(visible.some((job) => job.job_id === selectedId)).toBe(false);
    expect(selectVisibleJob(visible, selectedId)).toBe(visible[0]);
    expect(selectVisibleJob([], selectedId)).toBeNull();
  });
});
