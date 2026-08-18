import { render, screen } from "@testing-library/react";
import { JobTable } from "./JobTable";

describe("JobTable states", () => {
  it("renders a recoverable filtered empty state", () => {
    render(
      <JobTable
        jobs={[]}
        selectedId={null}
        hasFilters
        onSelect={() => undefined}
        onOpen={() => undefined}
      />,
    );
    expect(screen.getByText("没有符合筛选条件的任务")).toBeInTheDocument();
    expect(screen.getByText("清空搜索或更换状态筛选。")).toBeInTheDocument();
  });
});
