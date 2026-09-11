import { defineConfig, devices } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const port = process.env.REAL_E2E_PORT ?? "13180";
const apiPort = process.env.REAL_E2E_API_PORT ?? "18765";
const webMode = process.env.REAL_E2E_WEB_MODE ?? "development";
if (!["development", "production"].includes(webMode)) {
  throw new Error("REAL_E2E_WEB_MODE must be development or production");
}
for (const value of [port, apiPort]) {
  if (!/^\d+$/.test(value) || Number(value) < 1024 || Number(value) > 65535) {
    throw new Error("Real acceptance ports must be integers in 1024..65535");
  }
}
const root = process.env.REAL_E2E_ROOT ?? mkdtempSync(path.join(tmpdir(), "udify-real-e2e-"));
const api = `http://127.0.0.1:${apiPort}`;
process.env.REAL_E2E_ROOT = root;
process.env.REAL_E2E_API = api;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "real-workflow.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [
    ["line"],
    ["html", { outputFolder: path.join(root, "report"), open: "never" }],
    ["json", { outputFile: path.join(root, "report.json") }],
  ],
  outputDir: path.join(root, "results"),
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "real-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1024 } } },
    { name: "real-mobile", use: { ...devices["iPhone 13"], browserName: "chromium", viewport: { width: 390, height: 844 } } },
  ],
  webServer: [
    {
      command: `../.venv/bin/python -m udify.cli serve --host 127.0.0.1 --port ${apiPort} --state-dir "$REAL_E2E_ROOT/state"`,
      url: `${api}/api/v0/healthz`,
      reuseExistingServer: false,
      timeout: 30_000,
      stdout: "pipe",
      stderr: "pipe",
      env: { REAL_E2E_ROOT: root },
    },
    {
      command: `pnpm exec next ${webMode === "production" ? "start" : "dev"} --hostname 127.0.0.1 --port ${port}`,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: false,
      timeout: 120_000,
      stdout: "pipe",
      stderr: "pipe",
      env: { NEXT_PUBLIC_UDIFY_API: api },
    },
  ],
});
