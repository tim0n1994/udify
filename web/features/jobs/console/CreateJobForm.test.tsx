import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { CreateJobForm } from "./CreateJobForm";

describe("CreateJobForm", () => {
  it("blocks invalid input and submits trimmed valid values", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<CreateJobForm pending={false} apiError={null} onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: "创建任务" }));
    expect(screen.getByText("请输入游戏目录")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/游戏目录/), " /game ");
    await user.type(screen.getByLabelText(/改造意图/), " 让 Boss 更难 ");
    await user.click(screen.getByRole("button", { name: "创建任务" }));
    expect(onSubmit).toHaveBeenCalledWith({ gameRoot: "/game", intent: "让 Boss 更难" });
  });
});
