import { fireEvent, render, screen } from "@testing-library/react";
import { makeJob } from "@/test/fixtures";
import { OpsMatrix } from "./OpsMatrix";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("OpsMatrix", () => {
  it("aggregates job counts per status", () => {
    render(
      <OpsMatrix
        jobs={[
          makeJob({ job_id: "a", status: "awaiting_review" }),
          makeJob({ job_id: "b", status: "awaiting_review" }),
          makeJob({ job_id: "c", status: "failed" }),
        ]}
      />,
    );
    expect(screen.getByRole("gridcell", { name: /待审阅 2/ })).toBeInTheDocument();
    expect(screen.getByRole("gridcell", { name: /失败 1/ })).toBeInTheDocument();
    expect(screen.getByRole("gridcell", { name: /已拒绝 0/ })).toBeDisabled();
  });

  it("deep-links to the newest matching job", () => {
    render(<OpsMatrix jobs={[makeJob({ job_id: "job-x", status: "awaiting_review" })]} />);
    fireEvent.click(screen.getByRole("gridcell", { name: /待审阅 1/ }));
    expect(push).toHaveBeenCalledWith("/jobs/job-x");
  });
});
