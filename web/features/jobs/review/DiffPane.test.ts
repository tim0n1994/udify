import { buildDiffLines } from "./DiffPane";
import { planFixture } from "@/test/fixtures";

describe("DiffPane", () => {
  it("builds stable old/new line numbers for context, removals and additions", () => {
    const lines = buildDiffLines(planFixture.diffs[0]!);
    expect(lines.some((line) => line.kind === "remove" && line.oldLine === 2)).toBe(true);
    expect(lines.some((line) => line.kind === "add" && line.newLine === 2)).toBe(true);
    expect(lines.at(-1)).toMatchObject({ kind: "context", oldLine: 4, newLine: 4 });
  });
});
