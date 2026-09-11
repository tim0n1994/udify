import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ClarificationForm } from "./ClarificationForm";

const clarification = { question: "要修改哪个目标？", reason: "存在多个匹配项", graph_checksum: "abc", candidates: [{ node_id: "enemy:BossA", display_name: "BossA" }, { node_id: "enemy:BossC", display_name: "BossC" }] };

it("submits only selected persisted candidate IDs", async () => {
  const submit = vi.fn();
  const user = userEvent.setup();
  render(<ClarificationForm clarification={clarification} pending={false} onSubmit={submit} />);
  expect(screen.getByRole("button", { name: "确认目标并继续" })).toBeDisabled();
  await user.click(screen.getByRole("checkbox", { name: /BossA/ }));
  await user.click(screen.getByRole("button", { name: "确认目标并继续" }));
  expect(submit).toHaveBeenCalledWith(["enemy:BossA"]);
});

it("does not create an actionable choice when persisted candidates are missing", () => {
  render(<ClarificationForm clarification={{ question: "目标?" }} pending={false} onSubmit={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("目标候选不可用");
  expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
});

it("drops a selection no longer present in the backend candidates", async () => {
  const user = userEvent.setup();
  const { rerender } = render(<ClarificationForm clarification={clarification} pending={false} onSubmit={vi.fn()} />);
  await user.click(screen.getByRole("checkbox", { name: /BossA/ }));
  rerender(<ClarificationForm clarification={{ ...clarification, candidates: clarification.candidates.slice(1) }} pending={false} onSubmit={vi.fn()} />);
  expect(screen.getByRole("button", { name: "确认目标并继续" })).toBeDisabled();
});
