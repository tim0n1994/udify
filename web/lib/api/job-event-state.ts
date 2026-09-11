import type { JobEvent, JobStatus } from "./types";

export function mergeJobEvents(
  current: JobEvent[],
  incoming: JobEvent[],
  jobId: string,
): JobEvent[] {
  const eventsBySeq = new Map<number, JobEvent>();

  // Current records take precedence; the first valid record at each seq wins.
  for (const records of [current, incoming]) {
    for (const record of records) {
      if (
        record.job_id !== jobId ||
        !Number.isSafeInteger(record.seq) ||
        record.seq <= 0 ||
        eventsBySeq.has(record.seq)
      ) {
        continue;
      }

      eventsBySeq.set(record.seq, record);
    }
  }

  return Array.from(eventsBySeq.values()).sort((a, b) => a.seq - b.seq);
}

// Ends this observation epoch, not the job's ability to change later.
export function isTerminalStatus(
  status: JobStatus | null | undefined,
): boolean {
  return (
    status === "completed" ||
    status === "failed" ||
    status === "rejected" ||
    status === "rolled_back"
  );
}
