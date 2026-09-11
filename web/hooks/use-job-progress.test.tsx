import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useJobProgress } from "./use-job-progress";
import type { JobEvent, JobStatus } from "@/lib/api/types";
import { makeJob, ok } from "@/test/fixtures";

const { invalidate, runtimeConfig } = vi.hoisted(() => ({
  invalidate: vi.fn().mockResolvedValue(undefined),
  runtimeConfig: { apiBase: "http://127.0.0.1:9876" },
}));
const queryClient = { invalidateQueries: invalidate };
vi.mock("@tanstack/react-query", () => ({ useQueryClient: () => queryClient }));
vi.mock("@/lib/config", () => ({ useConfig: () => ({ config: runtimeConfig }) }));

class TestSource {
  static instances: TestSource[] = [];
  listeners = new Map<string, (event: MessageEvent) => void>();
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) { TestSource.instances.push(this); }
  addEventListener(name: string, handler: (event: MessageEvent) => void): void { this.listeners.set(name, handler); }
  emit(name: string, data: unknown): void { this.listeners.get(name)?.(new MessageEvent(name, { data: JSON.stringify(data) })); }
}

function event(seq: number, stage: JobStatus = "planning", jobId = "a"): JobEvent {
  return { job_id: jobId, seq, ts: 1700000000 + seq, stage, event: `event-${seq}`, payload: {}, record_hash: `h${seq}` };
}
function response(jobId: string, status: JobStatus, events: JobEvent[]): Response {
  return new Response(JSON.stringify(ok({ job: makeJob({ job_id: jobId, status }), events, audit_chain_valid: true })), { headers: { "Content-Type": "application/json" } });
}
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  TestSource.instances = [];
  fetchMock.mockReset().mockImplementation(async () => response("a", "planning", [event(1)]));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", TestSource);
  invalidate.mockClear();
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("canonical job observation", () => {
  it("uses runtime API base and deduplicates SSE replay against snapshot", async () => {
    const { result } = renderHook(() => useJobProgress("a"));
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    const source = TestSource.instances[0]!;
    expect(source.url).toBe("http://127.0.0.1:9876/api/v0/jobs/a/events?after_seq=0");
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("127.0.0.1:9876/api/v0/jobs/a");
    act(() => { source.emit("job", event(1)); source.emit("job", event(2, "awaiting_review")); source.emit("job", event(2, "awaiting_review")); });
    expect(result.current.events.map((item) => item.seq)).toEqual([1, 2]);
    expect(result.current.status).toBe("awaiting_review");
    expect(result.current.isDone).toBe(false);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["job", "a"] });
  });

  it("does not roll back a newer SSE status when an old snapshot resolves", async () => {
    let finish!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const { result } = renderHook(() => useJobProgress("a"));
    act(() => TestSource.instances[0]!.emit("job", event(3, "awaiting_clarification")));
    await act(async () => finish(response("a", "planning", [event(1), event(2)])));
    expect(result.current.status).toBe("awaiting_clarification");
    expect(result.current.events.map((item) => item.seq)).toEqual([1, 2, 3]);
    expect(result.current.isDone).toBe(false);
  });

  it("isolates stale requests and resets sequence when switching jobs", async () => {
    let finish!: (value: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; }));
    const { result, rerender } = renderHook(({ id }) => useJobProgress(id), { initialProps: { id: "a" } });
    act(() => TestSource.instances[0]!.emit("job", event(9)));
    fetchMock.mockImplementationOnce(async () => response("b", "planning", [event(1, "planning", "b")]));
    rerender({ id: "b" });
    await waitFor(() => expect(result.current.events[0]?.job_id).toBe("b"));
    await act(async () => finish(response("a", "failed", [event(10, "failed")])));
    expect(result.current.events.map((item) => item.job_id)).toEqual(["b"]);
    expect(result.current.status).toBe("planning");
    expect(TestSource.instances[0]!.close).toHaveBeenCalled();
    expect(TestSource.instances[1]!.url).toContain("/b/events?after_seq=0");
  });

  it("polls the canonical sequence and keeps waiting until a real terminal state", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useJobProgress("a"));
    await act(async () => {});
    fetchMock.mockImplementationOnce(async () => response("a", "awaiting_review", [event(2, "awaiting_review")]));
    await act(async () => { const source = TestSource.instances[0]!; source.onerror?.(); source.onerror?.(); source.onerror?.(); });
    expect(result.current.usingSse).toBe(false);
    expect(result.current.status).toBe("awaiting_review");
    expect(result.current.isDone).toBe(false);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("after_seq=1");
    fetchMock.mockImplementationOnce(async () => response("a", "failed", [event(3, "failed")]));
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.status).toBe("failed");
    expect(result.current.isDone).toBe(true);
    const calls = fetchMock.mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(6000));
    expect(fetchMock).toHaveBeenCalledTimes(calls);
  });

  it("parses done status and can reopen observation after a new lifecycle", async () => {
    const { result, rerender } = renderHook(({ key }) => useJobProgress("a", key), { initialProps: { key: "0" } });
    await waitFor(() => expect(result.current.events).toHaveLength(1));
    fetchMock.mockImplementationOnce(async () => response("a", "rejected", [event(2, "rejected")]));
    await act(async () => TestSource.instances[0]!.emit("done", { job_id: "a", status: "rejected", seq: 2 }));
    expect(result.current.status).toBe("rejected");
    expect(result.current.isDone).toBe(true);
    fetchMock.mockImplementationOnce(async () => response("a", "compensating", [event(3, "compensating")]));
    rerender({ key: "1" });
    await waitFor(() => expect(result.current.status).toBe("compensating"));
    expect(result.current.isDone).toBe(false);
    expect(TestSource.instances).toHaveLength(2);
  });
});
