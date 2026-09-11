import { describe, expect, it } from "vitest";
import { isTerminalStatus, mergeJobEvents } from "./job-event-state";
import type { JobEvent, JobStatus } from "./types";

function event(seq: number, jobId = "job-a", name = "stage_started"): JobEvent {
  return {
    job_id: jobId,
    seq,
    ts: 1_700_000_000 + seq,
    stage: "planning",
    event: name,
    payload: {},
    record_hash: `hash-${jobId}-${seq}`,
  };
}

describe("canonical job event merge", () => {
  it("merges overlapping snapshot and replay without duplicating sequence IDs", () => {
    const first = event(1);
    const second = event(2);
    expect(mergeJobEvents([first, second], [event(2), event(3)], "job-a"))
      .toEqual([first, second, event(3)]);
  });

  it("orders delayed events while preserving existing entries for the same sequence", () => {
    const persisted = event(2, "job-a", "approved");
    expect(mergeJobEvents([persisted], [event(3), event(1), event(2)], "job-a"))
      .toEqual([event(1), persisted, event(3)]);
  });

  it("drops events from both old state and stale responses after changing jobs", () => {
    expect(mergeJobEvents([event(9)], [event(10), event(1, "job-b")], "job-b"))
      .toEqual([event(1, "job-b")]);
  });

  it("does not mutate either input array", () => {
    const previous = [event(2)];
    const incoming = [event(3), event(1)];
    const before = JSON.stringify([previous, incoming]);
    mergeJobEvents(previous, incoming, "job-a");
    expect(JSON.stringify([previous, incoming])).toBe(before);
  });

  it("rejects invalid sequence numbers without losing valid events", () => {
    const invalid = [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY];
    expect(mergeJobEvents([], [...invalid.map((seq) => event(seq)), event(1)], "job-a"))
      .toEqual([event(1)]);
  });

  it("handles empty replay and repeated replay idempotently", () => {
    const once = mergeJobEvents([], [event(1), event(1)], "job-a");
    expect(mergeJobEvents(once, once, "job-a")).toEqual(once);
    expect(mergeJobEvents(once, [], "job-a")).toEqual(once);
  });
});

describe("observation terminal status", () => {
  it.each<JobStatus>(["completed", "failed", "rejected", "rolled_back"])(
    "closes the current observation stream for %s",
    (status) => expect(isTerminalStatus(status)).toBe(true),
  );

  it.each<JobStatus>([
    "created", "perceiving", "planning", "awaiting_clarification", "awaiting_review",
    "applying", "validating", "packaging", "compensating",
  ])("keeps waiting or active %s open", (status) => {
    expect(isTerminalStatus(status)).toBe(false);
  });

  it("does not classify absent status as complete", () => {
    expect(isTerminalStatus(null)).toBe(false);
    expect(isTerminalStatus(undefined)).toBe(false);
  });
});
