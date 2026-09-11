import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { JobActions } from "./JobActions";
import { detailFixture, planFixture } from "@/test/fixtures";

describe("JobActions", () => {
  it("disables an already-open confirmation when audit validation is lost", async () => {
    const user = userEvent.setup();
    const props = { job: detailFixture.job, plan: planFixture, highestRisk: 0.1,
      approvePending: false, rejectPending: false, rollbackPending: false,
      onApprove: vi.fn(), onReject: vi.fn(), onRollback: vi.fn() };
    const { rerender } = render(<JobActions {...props} auditValid={true} />);
    await user.click(screen.getByRole("button", { name: "批准并应用" }));
    rerender(<JobActions {...props} auditValid={false} />);
    expect(screen.getByRole("button", { name: "确认批准" })).toBeDisabled();
  });
  it.each([false, null])("blocks approval for audit state %s", (auditValid) => {
    render(<JobActions job={detailFixture.job} plan={planFixture} auditValid={auditValid} highestRisk={0.1}
      approvePending={false} rejectPending={false} rollbackPending={false}
      onApprove={vi.fn()} onReject={vi.fn()} onRollback={vi.fn()} />);
    expect(screen.getByRole("button", { name: "批准并应用" })).toBeDisabled();
  });
  it("opens an accessible approval dialog with review facts", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    render(
      <JobActions
        job={detailFixture.job}
        plan={planFixture}
        auditValid={true}
        highestRisk={0.45}
        approvePending={false}
        rejectPending={false}
        rollbackPending={false}
        onApprove={onApprove}
        onReject={vi.fn()}
        onRollback={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: "批准并应用" }));
    expect(screen.getByRole("alertdialog", { name: "批准并应用到 VFS？" })).toBeInTheDocument();
    expect(screen.getByText("R2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "确认批准" }));
    expect(onApprove).toHaveBeenCalledOnce();
  });
});
