import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { JobActions } from "./JobActions";
import { detailFixture, planFixture } from "@/test/fixtures";

describe("JobActions", () => {
  it("opens an accessible approval dialog with review facts", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    render(
      <JobActions
        job={detailFixture.job}
        plan={planFixture}
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
