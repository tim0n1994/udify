import { render, screen } from "@testing-library/react";
import { ReportEvidence } from "./ReportEvidence";
import { ProbeView } from "@/components/ProbeView";
import { reportFixture } from "@/test/fixtures";
import { reportSchema } from "@/lib/api/schema";

it("preserves and renders package-only static evidence from the API contract", () => {
  const report = reportSchema.parse({ ...reportFixture,
    engine_coverage: "STATIC_PROXY",
    delivery: { kind: "package", installed: false, tier: "STATIC_ONLY", reason: "INI artifact checks only" },
    artifact_validation: { passed: true, checks: [{ name: "parse_ini", passed: true, detail: "BossA HP=200" }] },
    gate_verdict: { final_tier: 2, final_tier_reason: "static validation", gates: [{ name: "validation", lifecycle: "complete", verdict: "passed", evidence: { engine: "miu2d" }, delivery_tier: 2 }] },
  });
  render(<><ReportEvidence report={report} /><ProbeView report={report} /></>);
  expect(screen.getByText("仅生成 Mod 包，未安装到游戏")).toBeInTheDocument();
  expect(screen.getByText("仅进行静态检查，未运行游戏验证。")).toBeInTheDocument();
  expect(screen.getByText(/BossA HP=200/)).toBeInTheDocument();
  expect(screen.getByText(/"engine": "miu2d"/)).toBeInTheDocument();
  expect(screen.getAllByText("未验证")).toHaveLength(2);
});

it("does not claim static checks passed when artifact validation failed", () => {
  const report = reportSchema.parse({ ...reportFixture,
    static_validation: { ...reportFixture.static_validation, passed: false, error_count: 1 },
    delivery: { kind: "package", installed: false, tier: "STATIC_ONLY", reason: "artifact validation blocked" },
    artifact_validation: { passed: false, checks: [{ name: "parse_ini", passed: false, detail: "Invalid section" }] },
  });
  render(<ReportEvidence report={report} />);
  expect(screen.getByText("仅进行静态检查，未运行游戏验证。")).toBeInTheDocument();
  expect(screen.queryByText(/仅通过静态检查/)).not.toBeInTheDocument();
  expect(screen.getByText("产物检查：未通过")).toBeInTheDocument();
});

it("distinguishes downgrade policy from performed runtime or dependency checks", () => {
  const report = reportSchema.parse({ ...reportFixture,
    delivery: { kind: "package", installed: false, tier: "STATIC_ONLY", reason: "not executed" },
    gate_verdict: { final_tier: 1, final_tier_reason: "static only", gates: [
      { name: "runtime_validation", lifecycle: "decided", verdict: "pass", evidence: "not executed", delivery_tier: 1 },
      { name: "dependency", lifecycle: "decided", verdict: "pass", evidence: "not evaluated", delivery_tier: 3 },
    ] },
  });
  render(<ReportEvidence report={report} />);
  expect(screen.getByText("运行验证门").parentElement).toHaveTextContent("允许降级交付");
  expect(screen.getByText("依赖兼容门").parentElement).toHaveTextContent("未评估（仅生成包）");
  expect(screen.queryByText(/· pass ·/)).not.toBeInTheDocument();
});

it("does not claim runtime measurements for skipped probes with historical positive coverage", () => {
  const report = reportSchema.parse({ ...reportFixture,
    engine_coverage: "NATIVE_HEADLESS",
    probe: { ...reportFixture.probe, skipped: true },
  });
  render(<ProbeView report={report} />);
  expect(screen.getByText("未执行")).toBeInTheDocument();
  expect(screen.getAllByText("未验证")).toHaveLength(2);
  expect(screen.getByText("未采集")).toBeInTheDocument();
  expect(screen.queryByText("是")).not.toBeInTheDocument();
});

it("treats missing historical coverage as unknown despite passed probe booleans", () => {
  render(<><ReportEvidence report={reportFixture} /><ProbeView report={reportFixture} /></>);
  expect(screen.getByText("交付范围未知")).toBeInTheDocument();
  expect(screen.getAllByText("未验证")).toHaveLength(2);
  expect(screen.getByText("未采集")).toBeInTheDocument();
});
