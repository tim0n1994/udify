import { makeJob } from "@/test/fixtures";
import { buildHeatCells, dominantCell } from "./heat";

describe("heat matrix", () => {
  it("keeps persisted clarification tasks visible as a waiting gate", () => {
    const job = makeJob({ status: "awaiting_clarification" });
    expect(buildHeatCells([job]).find((cell) => cell.status === "awaiting_clarification"))
      .toMatchObject({ label: "待确认目标", tone: "gate", jobs: [job] });
  });
  it("groups jobs by status in canonical order", () => {
    const cells = buildHeatCells([
      makeJob({ job_id: "a", status: "completed" }),
      makeJob({ job_id: "b", status: "awaiting_review" }),
      makeJob({ job_id: "c", status: "awaiting_review" }),
      makeJob({ job_id: "d", status: "failed" }),
    ]);
    expect(cells[0]).toMatchObject({
      status: "awaiting_review",
      jobs: [
        expect.objectContaining({ job_id: "b" }),
        expect.objectContaining({ job_id: "c" }),
      ],
    });
    expect(cells.at(-1)?.status).toBe("rejected");
  });

  it("dominantCell picks the largest bucket", () => {
    const cells = buildHeatCells([
      makeJob({ job_id: "a", status: "completed" }),
      makeJob({ job_id: "b", status: "awaiting_review" }),
      makeJob({ job_id: "c", status: "awaiting_review" }),
    ]);
    expect(dominantCell(cells)?.status).toBe("awaiting_review");
  });
});
