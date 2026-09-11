import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { JobProgressPanel } from "./job-progress-panel";
import { useJobProgress } from "@/hooks/use-job-progress";
import type { JobProgressState } from "@/hooks/use-job-progress";

vi.mock("@/hooks/use-job-progress", () => ({ useJobProgress: vi.fn() }));
const mocked = vi.mocked(useJobProgress);

function state(overrides: Partial<JobProgressState> = {}): JobProgressState {
  return { events: [], latest: null, status: null, isDone: false, usingSse: true, connected: false, error: null, ...overrides };
}

describe("JobProgressPanel", () => {
  it("renders waiting without invented percentages", () => {
    mocked.mockReturnValue(state());
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("等待开始")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it.each(["awaiting_review", "awaiting_clarification"] as const)("keeps %s visibly waiting", (status) => {
    mocked.mockReturnValue(state({ status }));
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText(status === "awaiting_review" ? "待审阅" : "待确认目标")).toBeInTheDocument();
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
  });

  it("ends a failed stream without success indicators", () => {
    mocked.mockReturnValue(state({ status: "failed", isDone: true }));
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("失败")).toBeInTheDocument();
    expect(screen.getByText("订阅已结束")).toBeInTheDocument();
    expect(screen.queryByText("已完成")).not.toBeInTheDocument();
  });

  it("shows degraded transport and canonical persisted events", () => {
    mocked.mockReturnValue(state({ usingSse: false, events: [{ job_id: "job-1", seq: 4, ts: 1700000000, stage: "planning", event: "planning_started", payload: {}, record_hash: "h4" }] }));
    render(<JobProgressPanel jobId="job-1" lifecycleKey="2" status="planning" />);
    expect(screen.getByText("轮询")).toBeInTheDocument();
    expect(screen.getByText("planning_started")).toBeInTheDocument();
    expect(mocked).toHaveBeenLastCalledWith("job-1", "2", "planning");
  });
});
