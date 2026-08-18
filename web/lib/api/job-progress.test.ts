import { describe, it, expect } from "vitest";
import {
  progressEventSchema,
  progressStageSchema,
  progressDoneSchema,
} from "./job-progress";

describe("progressStageSchema", () => {
  it("accepts all five stages", () => {
    for (const stage of ["perceiving", "planning", "applying", "validating", "packaging"]) {
      expect(progressStageSchema.safeParse(stage).success).toBe(true);
    }
  });

  it("rejects unknown stages", () => {
    expect(progressStageSchema.safeParse("unknown").success).toBe(false);
  });
});

describe("progressEventSchema", () => {
  it("parses a complete event matching the Python ProgressEvent shape", () => {
    const raw = {
      job_id: "abc123",
      stage: "planning",
      detail: "MCTS step 3/10",
      pct: 30.0,
      current: 3,
      total: 10,
      timestamp: "2026-08-06T05:00:00Z",
      seq: 3,
    };
    const parsed = progressEventSchema.parse(raw);
    expect(parsed.stage).toBe("planning");
    expect(parsed.pct).toBe(30.0);
    expect(parsed.seq).toBe(3);
  });

  it("applies defaults for missing optional fields", () => {
    const parsed = progressEventSchema.parse({
      job_id: "j1",
      stage: "perceiving",
      timestamp: "2026-08-06T05:00:00Z",
      seq: 0,
    });
    expect(parsed.detail).toBe("");
    expect(parsed.pct).toBe(0);
    expect(parsed.current).toBe(0);
  });

  it("rejects pct out of range", () => {
    expect(
      progressEventSchema.safeParse({
        job_id: "j1",
        stage: "planning",
        pct: 150,
        timestamp: "t",
        seq: 1,
      }).success,
    ).toBe(false);
  });
});

describe("progressDoneSchema", () => {
  it("parses a terminal-status event", () => {
    const parsed = progressDoneSchema.parse({ job_id: "j1", status: "completed" });
    expect(parsed.status).toBe("completed");
  });
});
