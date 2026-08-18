import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock the hook so the component test is deterministic and does not need a real EventSource.
vi.mock("@/hooks/use-job-progress", () => ({
  useJobProgress: vi.fn(),
}));

import { JobProgressPanel } from "./job-progress-panel";
import { useJobProgress } from "@/hooks/use-job-progress";

const mockedUseJobProgress = vi.mocked(useJobProgress);

function mockState(overrides: Partial<ReturnType<typeof useJobProgress>> = {}) {
  return {
    events: [],
    latest: null,
    isDone: false,
    usingSse: true,
    error: null,
    ...overrides,
  };
}

describe("JobProgressPanel", () => {
  it("renders waiting state when no events yet", () => {
    mockedUseJobProgress.mockReturnValue(mockState());
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("等待开始")).toBeInTheDocument();
    expect(screen.getByText("SSE")).toBeInTheDocument();
  });

  it("renders the current stage and progress percentage", () => {
    mockedUseJobProgress.mockReturnValue(
      mockState({
        latest: {
          job_id: "job-1",
          stage: "planning",
          detail: "MCTS step 5/10",
          pct: 50,
          current: 5,
          total: 10,
          timestamp: "2026-08-06T05:00:00Z",
          seq: 5,
        },
      }),
    );
    render(<JobProgressPanel jobId="job-1" />);
    // "规划" appears in both the progress label and the timeline; assert at least one
    expect(screen.getAllByText("规划").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("MCTS step 5/10")).toBeInTheDocument();
  });

  it("shows completion badge when isDone", () => {
    mockedUseJobProgress.mockReturnValue(mockState({ isDone: true }));
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("完成")).toBeInTheDocument();
  });

  it("shows polling badge when degraded from SSE", () => {
    mockedUseJobProgress.mockReturnValue(mockState({ usingSse: false, error: "polling failed" }));
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("轮询")).toBeInTheDocument();
  });

  it("renders the five-stage timeline", () => {
    mockedUseJobProgress.mockReturnValue(mockState());
    render(<JobProgressPanel jobId="job-1" />);
    for (const label of ["感知", "规划", "应用", "验证", "打包"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("renders recent event stream entries", () => {
    mockedUseJobProgress.mockReturnValue(
      mockState({
        events: [
          {
            job_id: "job-1",
            stage: "perceiving",
            detail: "scan file 1",
            pct: 10,
            current: 1,
            total: 10,
            timestamp: "t",
            seq: 1,
          },
          {
            job_id: "job-1",
            stage: "planning",
            detail: "step 2",
            pct: 20,
            current: 2,
            total: 10,
            timestamp: "t",
            seq: 2,
          },
        ],
      }),
    );
    render(<JobProgressPanel jobId="job-1" />);
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getByText("#2")).toBeInTheDocument();
  });
});
