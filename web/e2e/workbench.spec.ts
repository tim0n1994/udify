import { expect, test } from "@playwright/test";
import { installMockApi } from "./mock-api";

const DETAIL_INTENT = "让第一个 Boss 更难，但不要单纯翻倍血量";

test.beforeEach(async ({ page }) => {
  await installMockApi(page);
});

test("cockpit filters, opens review, persists tab URL and confirms approval", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Udify/);
  await expect(page.getByRole("heading", { name: "证据驾驶舱" })).toBeVisible();

  // C-01 MissionStrip 反映真实的 job 盘点
  await expect(page.getByText(/\d+ 活跃 · \d+ 待批准 · \d+ 总任务/)).toBeVisible();

  // C-03b 任务流：五份 fixture 记录渲染成五行
  const rows = page.getByRole("row");
  await expect(rows.filter({ hasText: "让第一个 Boss 更难" })).toBeVisible();
  await expect(rows.filter({ hasText: "回滚敌人血量修改" })).toBeVisible();
  await expect(rows.filter({ hasText: "调整新手区治疗资源" })).toBeVisible();
  await expect(rows.filter({ hasText: "修复 NPC 奖励配置" })).toBeVisible();
  await expect(rows.filter({ hasText: "修改危险 Lua 脚本" })).toBeVisible();

  // 搜索筛选： deposits NPC-only；补集消失
  await page.getByPlaceholder("搜索意图、目录或 Job ID").fill("NPC");
  await expect(rows.filter({ hasText: "修复 NPC 奖励配置" })).toBeVisible();
  await expect(rows.filter({ hasText: "修改危险 Lua" })).toHaveCount(0);
  await page.getByRole("button", { name: "清空筛选" }).click();

  // 状态筛选： 切到 failed 只剩一条危险 Lua 任务
  await page.getByRole("combobox", { name: "任务状态" }).selectOption("failed");
  await expect(rows.filter({ hasText: "修改危险 Lua" })).toBeVisible();
  await expect(rows.filter({ hasText: "让第一个 Boss 更难" })).toHaveCount(0);
  await page.getByRole("button", { name: "清空筛选" }).click();

  // 键盘流： 聚焦行 → Enter 深链到审阅页； URL 透出默认 tab=changes
  const targetRow = rows.filter({ hasText: "让第一个 Boss 更难" });
  await targetRow.focus();
  await targetRow.press("Enter");
  await page.waitForURL(/\/jobs\/job-review-001\?tab=changes$/);

  // 审阅页： 以 job 意图作为页面主角； changes tab 默认活跃
  await expect(page.getByRole("heading", { name: DETAIL_INTENT })).toBeVisible();
  // W1 新增： 审计条印章与任务详情同屏
  await expect(page.getByRole("status", { name: /审计链/ })).toBeVisible();
  await expect(
    page.getByRole("tab", { name: "修改计划" }),
  ).toHaveAttribute("data-state", "active");
  await expect(page.getByText("config/enemy.ini", { exact: true }).first()).toBeVisible();

  // tab 切换持久化到 URL
  await page.getByRole("tab", { name: "风险审阅" }).click();
  await page.waitForURL(/tab=risk/);

  // Radix alertdialog 审批流： 触发 → 确认 → 关闭
  await page.getByRole("button", { name: "批准并应用" }).click();
  const dialog = page.getByRole("alertdialog", { name: "批准并应用到 VFS？" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("R2")).toBeVisible();
  await dialog.getByRole("button", { name: "确认批准" }).click();
  await expect(dialog).not.toBeVisible();

  // 桌面 / 移动 viewport 都不允许水平溢出
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});

test("offline API shows a retryable ErrorRecord", async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
  let attempts = 0;
  await page.route("http://127.0.0.1:8765/api/v0/**", async (route) => {
    attempts += 1;
    await route.abort("connectionrefused");
  });
  await page.goto("/");
  await expect(page.getByText("API_CONN_REFUSED")).toBeVisible();
  const before = attempts;
  await page.getByRole("button", { name: /重试/ }).click();
  await expect.poll(() => attempts).toBeGreaterThan(before);
});

test("OpsMatrix deep-links to newest matching job", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "证据驾驶舱" })).toBeVisible();
  const cell = page.getByRole("gridcell", { name: /待审阅 1/ });
  await expect(cell).toBeVisible();
  await cell.click();
  await page.waitForURL(/\/jobs\/job-review-001/);
  await expect(page.getByRole("heading", { name: DETAIL_INTENT })).toBeVisible();
});

test("command palette opens via button and filters jobs", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "打开命令面板" }).click();
  const dialog = page.getByRole("dialog", { name: "命令面板" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox", { name: "检索命令" }).fill("NPC");
  // 检索结果是行按钮； mock API 总是返回同一 detail fixture，所以校验导航到达即可
  const option = dialog.getByRole("option", { name: /修复 NPC 奖励配置/ }).first();
  await expect(option).toBeVisible();
  await option.click();
  await page.waitForURL(/\/jobs\/job-done-003/);
  await expect(page.getByRole("status", { name: /审计链/ })).toBeVisible();
});
