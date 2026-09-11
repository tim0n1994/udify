import { render, screen } from "@testing-library/react";
import { ProbeView } from "./ProbeView";
import { reportFixture } from "@/test/fixtures";
import type { Report } from "@/lib/api";

const positiveProbe = {
  ...reportFixture.probe,
  results: [{ ...reportFixture.probe.results[0]!, probe_id: "START", passed: true }],
};
const modernDelivery: NonNullable<Report["delivery"]> = {
  kind: "package", installed: false, tier: "VERIFIED_ARTIFACT", reason: "Runtime evidence recorded",
};

it.each(["NATIVE_HEADLESS", "AUTOMATED_NON_HEADLESS"])("treats legacy %s coverage without execution records as unknown", (engine_coverage) => {
  const { container } = render(<ProbeView report={{ ...reportFixture, engine_coverage, probe: positiveProbe }} />);
  expect(screen.getByText("未执行")).toBeInTheDocument();
  expect(screen.getAllByText("未验证")).toHaveLength(2);
  expect(screen.getByText("未采集")).toBeInTheDocument();
  expect(screen.getByText("START")).toBeInTheDocument();
  expect(screen.getByText("记录未验证")).toBeInTheDocument();
  expect(screen.queryByText("是")).not.toBeInTheDocument();
  expect(container.querySelector(".text-ok")).toBeNull();
});

it("keeps explicitly skipped probes unverified even with positive coverage and delivery metadata", () => {
  const { container } = render(<ProbeView report={{ ...reportFixture, engine_coverage: "NATIVE_HEADLESS", delivery: modernDelivery, probe: { ...positiveProbe, skipped: true } }} />);
  expect(screen.getByText("未执行")).toBeInTheDocument();
  expect(screen.getByText("记录未验证")).toBeInTheDocument();
  expect(container.querySelector(".text-ok")).toBeNull();
});

it("requires explicit non-static delivery even when a probe says it was not skipped", () => {
  render(<ProbeView report={{ ...reportFixture, engine_coverage: "NATIVE_HEADLESS", probe: { ...positiveProbe, skipped: false } }} />);
  expect(screen.getByText("记录未验证")).toBeInTheDocument();
  expect(screen.queryByText("是")).not.toBeInTheDocument();
});

it("shows measured results when modern execution evidence is explicit", () => {
  const { container } = render(<ProbeView report={{ ...reportFixture, engine_coverage: "NATIVE_HEADLESS", delivery: modernDelivery, probe: { ...positiveProbe, skipped: false } }} />);
  expect(screen.getAllByText("是")).toHaveLength(2);
  expect(screen.getByText("1/1")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
  expect(screen.queryByText("记录未验证")).not.toBeInTheDocument();
  expect(container.querySelector(".text-ok")).not.toBeNull();
});

it("shows failed modern execution as negative measurements rather than unknown or successful", () => {
  const { container } = render(<ProbeView report={{
    ...reportFixture,
    engine_coverage: "NATIVE_HEADLESS",
    delivery: { ...modernDelivery, tier: "UNVERIFIED_ARTIFACT" },
    probe: {
      ...positiveProbe,
      skipped: false,
      passed: false,
      game_started: false,
      state_readable: false,
      console_error_count: 2,
      results: [{ ...positiveProbe.results[0]!, passed: false, console_errors: ["boot failed", "state unavailable"], evidence: "Runtime startup failed" }],
    },
  }} />);
  const negativeMeasurements = screen.getAllByText("否");
  expect(negativeMeasurements).toHaveLength(2);
  for (const measurement of negativeMeasurements) expect(measurement).toHaveClass("text-err");
  expect(screen.getByText("2")).toHaveClass("text-err");
  expect(screen.getByText("0/1")).toHaveClass("text-err");
  expect(screen.getByText("✗")).toHaveClass("text-err");
  expect(screen.getByText("Runtime startup failed")).toBeInTheDocument();
  expect(screen.queryByText("记录未验证")).not.toBeInTheDocument();
  expect(screen.queryByText("未验证")).not.toBeInTheDocument();
  expect(container.querySelector(".text-ok")).toBeNull();
});

it("does not promote static-only artifacts to runtime success", () => {
  const { container } = render(<ProbeView report={{ ...reportFixture, engine_coverage: "NATIVE_HEADLESS", delivery: { ...modernDelivery, tier: "STATIC_ONLY" }, probe: { ...positiveProbe, skipped: false } }} />);
  expect(screen.getByText("START")).toBeInTheDocument();
  expect(screen.getByText("记录未验证")).toBeInTheDocument();
  expect(container.querySelector(".text-ok")).toBeNull();
});
