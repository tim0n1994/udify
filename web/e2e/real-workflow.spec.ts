import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, readdirSync, realpathSync, writeFileSync } from "node:fs";
import path from "node:path";

const api = process.env.REAL_E2E_API;
const runRoot = process.env.REAL_E2E_ROOT;
test.skip(!api || !runRoot, "Run with playwright.real.config.ts and its isolated real services");

function prepareGame() {
  const game = mkdtempSync(path.join(runRoot!, "game-"));
  cpSync(path.resolve("../tests/fixtures/miu2d/product"), game, { recursive: true });
  for (const file of readdirSync(game)) {
    const destination = path.join(game, file);
    writeFileSync(destination, readFileSync(destination, "utf8").replace(/\r?\n/g, "\r\n"));
  }
  const original = Object.fromEntries(readdirSync(game).map((file) => [file, readFileSync(path.join(game, file))]));
  return { game, original };
}

async function createFromBrowser(page: Page, game: string, intent: string) {
  const healthResponse = page.waitForResponse((response) => response.url() === `${api}/api/v0/healthz` && response.request().method() === "GET");
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const health = await healthResponse;
  expect((await health.json()).data.state_dir).toBe(path.join(realpathSync(runRoot!), "state"));
  await expect(page.getByText("API 在线", { exact: true }).first()).toBeVisible();
  await page.getByLabel("游戏目录", { exact: true }).fill(game);
  await page.getByLabel(/改造意图/).fill(intent);
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await page.waitForURL(/\/jobs\/[^/?]+/, { waitUntil: "domcontentloaded" });
  return new URL(page.url()).pathname.split("/").at(-1)!;
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
}

test("real browser approval downloads exact package and revokes delivery", async ({ page, request }, testInfo) => {
  const { game, original } = prepareGame();
  let interruptedStreams = 0;
  if (testInfo.project.name === "real-mobile") {
    await page.route(/\/api\/v0\/jobs\/[^/]+\/events(?:\?|$)/, async (route) => {
      interruptedStreams += 1;
      await route.abort("connectionfailed");
    });
  }
  const jobId = await createFromBrowser(page, game, "把第一个 Boss 的攻击力翻倍");
  const endpoint = `${api}/api/v0/jobs/${jobId}`;
  await page.getByRole("tab", { name: "风险审阅" }).click();
  const approval = page.getByRole("button", { name: "批准并应用", exact: true });
  await expect(approval).toBeEnabled();
  const plan = (await (await request.get(`${endpoint}/plan`)).json()).data;
  expect(plan.operations).toHaveLength(1);
  expect(JSON.stringify(plan.operations)).toContain("BossA");
  expect(JSON.stringify(plan.operations)).toContain("Attack");
  await expect(page.getByRole("region", { name: "任务进度" })).toBeVisible();
  await noOverflow(page);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(approval).toBeEnabled();
  await approval.click();
  await page.getByRole("alertdialog").getByRole("button", { name: "确认批准" }).click();
  await page.getByRole("tab", { name: /报告/ }).click();
  const evidence = page.getByRole("region", { name: "交付证据" });
  await expect(evidence).toBeVisible();
  await expect(evidence.getByText("仅生成 Mod 包，未安装到游戏")).toBeVisible();
  await expect(evidence.getByText("仅进行静态检查，未运行游戏验证。")).toBeVisible();
  const report = (await (await request.get(`${endpoint}/report`)).json()).data;
  expect(report.delivery).toMatchObject({ kind: "package", installed: false, tier: "STATIC_ONLY" });
  expect(report.artifact_validation.passed).toBe(true);
  const downloadPending = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 ModPackage" }).click();
  const download = await downloadPending;
  const zip = testInfo.outputPath(`${jobId}.zip`);
  await download.saveAs(zip);
  const contents: Record<string, string> = JSON.parse(execFileSync(path.resolve("../.venv/bin/python"), [
    "-c", "import base64,json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps({n:base64.b64encode(z.read(n)).decode() for n in z.namelist()}))", zip,
  ], { encoding: "utf8" }));
  expect(Object.keys(contents).filter((name) => name.startsWith("files/"))).toEqual(["files/characters.ini"]);
  const expected = Buffer.from(original["characters.ini"]!.toString().replace("Attack=50\r\n", "Attack=100\r\n"));
  expect(Buffer.from(contents["files/characters.ini"]!, "base64")).toEqual(expected);
  for (const [file, bytes] of Object.entries(original)) {
    expect(readFileSync(path.join(game, file))).toEqual(bytes);
  }
  await page.screenshot({ path: testInfo.outputPath("completed-report.png"), fullPage: true });
  await noOverflow(page);
  await page.getByRole("tab", { name: "风险审阅" }).click();
  await page.getByRole("button", { name: "回滚并作废包" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "确认回滚" }).click();
  await expect.poll(async () => (await request.get(`${endpoint}/package`)).status()).toBe(404);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: /报告/ }).click();
  await expect(page.getByRole("link", { name: "下载 ModPackage" })).toHaveCount(0);
  await expect(page.getByText("Mod 包已作废，不能再下载；未对游戏执行安装或反向安装。")).toBeVisible();
  for (const [file, bytes] of Object.entries(original)) {
    expect(readFileSync(path.join(game, file))).toEqual(bytes);
  }
  if (testInfo.project.name === "real-mobile") expect(interruptedStreams).toBeGreaterThan(0);
  await testInfo.attach("real-job", { body: JSON.stringify({ jobId, game, endpoint, interruptedStreams, report }, null, 2), contentType: "application/json" });
});

test("real browser clarified target survives history and delivers exact revocable package", async ({ page, request }, testInfo) => {
  const { game, original } = prepareGame();
  const intent = "把 Boss 的攻击力翻倍";
  const jobId = await createFromBrowser(page, game, intent);
  const endpoint = `${api}/api/v0/jobs/${jobId}`;
  await expect(page.getByRole("checkbox", { name: /BossA/ })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /BossC/ })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Hero/ })).toHaveCount(0);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("checkbox", { name: /BossC/ })).toBeVisible();
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("API 在线", { exact: true }).first()).toBeVisible();
  await page.getByPlaceholder("搜索意图、目录或 Job ID").fill(jobId);
  await page.getByRole("button", { name: `打开任务 ${jobId}`, exact: true }).click();
  await page.waitForURL(new RegExp(`/jobs/${jobId}`), { waitUntil: "domcontentloaded" });
  await page.getByRole("checkbox", { name: /BossC/ }).check();
  await page.getByRole("button", { name: "确认目标并继续" }).click();
  await page.getByRole("tab", { name: "风险审阅" }).click();
  await expect(page.getByRole("button", { name: "批准并应用", exact: true })).toBeEnabled();
  const plan = (await (await request.get(`${endpoint}/plan`)).json()).data;
  expect(plan.operations).toHaveLength(1);
  expect(JSON.stringify(plan.operations)).toContain("BossC");
  await noOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("clarified-review.png"), fullPage: true });
  for (const [file, bytes] of Object.entries(original)) {
    expect(readFileSync(path.join(game, file))).toEqual(bytes);
  }
  await page.getByRole("button", { name: "批准并应用", exact: true }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "确认批准" }).click();
  await page.getByRole("tab", { name: "验证报告", exact: true }).click();
  const evidence = page.getByRole("region", { name: "交付证据" });
  await expect(evidence.getByText("仅生成 Mod 包，未安装到游戏")).toBeVisible();
  await expect(evidence.getByText("仅进行静态检查，未运行游戏验证。")).toBeVisible();
  const report = (await (await request.get(`${endpoint}/report`)).json()).data;
  expect(report.delivery).toMatchObject({ kind: "package", installed: false, tier: "STATIC_ONLY" });
  expect(report.artifact_validation.passed).toBe(true);
  const downloadPending = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载 ModPackage" }).click();
  const download = await downloadPending;
  const zip = testInfo.outputPath(`${jobId}-BossC.zip`);
  await download.saveAs(zip);
  const contents: Record<string, string> = JSON.parse(execFileSync(path.resolve("../.venv/bin/python"), [
    "-c", "import base64,json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps({n:base64.b64encode(z.read(n)).decode() for n in z.namelist()}))", zip,
  ], { encoding: "utf8" }));
  expect(Object.keys(contents).filter((name) => name.startsWith("files/"))).toEqual(["files/characters.ini"]);
  const expected = Buffer.from(original["characters.ini"]!.toString().replace("Attack=90\r\n", "Attack=180\r\n"));
  expect(Buffer.from(contents["files/characters.ini"]!, "base64")).toEqual(expected);
  for (const [file, bytes] of Object.entries(original)) {
    expect(readFileSync(path.join(game, file))).toEqual(bytes);
  }
  await noOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("clarified-completed-report.png"), fullPage: true });
  await page.getByRole("tab", { name: "风险审阅", exact: true }).click();
  await page.getByRole("button", { name: "回滚并作废包" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "确认回滚" }).click();
  await expect.poll(async () => (await request.get(`${endpoint}/package`)).status()).toBe(404);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("link", { name: "下载 ModPackage" })).toHaveCount(0);
  await expect(page.getByText("Mod 包已作废，不能再下载；未对游戏执行安装或反向安装。")).toBeVisible();
  for (const [file, bytes] of Object.entries(original)) {
    expect(readFileSync(path.join(game, file))).toEqual(bytes);
  }
  await noOverflow(page);
  await page.screenshot({ path: testInfo.outputPath("clarified-revoked.png"), fullPage: true });
  await testInfo.attach("clarified-real-job", { body: JSON.stringify({ jobId, game, endpoint, selectedTarget: "BossC", report }, null, 2), contentType: "application/json" });
});
