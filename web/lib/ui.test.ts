import { riskLevel, STATUS_META } from "./ui";
import { jobStatusSchema } from "./api/schema";

describe("status and risk presentation mappings", () => {
  it("maps every durable terminal/intermediate status", () => {
    expect(Object.keys(STATUS_META)).toEqual(jobStatusSchema.options);
    expect(STATUS_META.awaiting_clarification).toMatchObject({ label: "待确认目标", tone: "gate" });
    expect(STATUS_META.awaiting_review).toMatchObject({ label: "待审阅", tone: "gate" });
    expect(STATUS_META.failed.tone).toBe("err");
    expect(STATUS_META.rolled_back.label).toBe("已回滚");
  });

  it.each([
    [0.1, 0], [0.2, 1], [0.4, 2], [0.6, 3], [0.9, 4],
  ])("maps risk %s to R%s", (risk, level) => {
    expect(riskLevel(risk)).toBe(level);
  });
});
