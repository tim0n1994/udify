import { render, screen } from "@testing-library/react";
import { AuditTreatySeal } from "./AuditTreatySeal";

it("does not present unverified audit state as valid", () => {
  render(<AuditTreatySeal valid={null} events={[]} jobId="job-1" />);
  expect(screen.getByRole("status")).toHaveAccessibleName("任务 job-1 审计链尚未校验");
  expect(screen.getByRole("status")).toHaveAttribute("data-valid", "unknown");
  expect(screen.queryByText(/链完整/)).not.toBeInTheDocument();
});
