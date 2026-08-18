import type { Page, Route } from "@playwright/test";
import { detailFixture, jobsFixture, ok, planFixture, reportFixture } from "@/test/fixtures";

const apiPrefix = "http://127.0.0.1:8765/api/v0";

function json(route: Route, data: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
}

export async function installMockApi(page: Page) {
  await page.route(`${apiPrefix}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path.endsWith("/healthz")) return json(route, ok({ version: "e2e", engines: { miu2d: true } }));
    if (path === "/api/v0/jobs" && request.method() === "GET") return json(route, ok(jobsFixture));
    if (path.endsWith("/plan")) return json(route, ok(planFixture));
    if (path.endsWith("/report")) return json(route, ok(reportFixture));
    if (path.endsWith("/approve") && request.method() === "POST") {
      return json(route, ok({ ...detailFixture.job, status: "applying" }));
    }
    if (path.endsWith("/reject") && request.method() === "POST") {
      return json(route, ok({ ...detailFixture.job, status: "rejected" }));
    }
    if (/\/api\/v0\/jobs\/[^/]+$/.test(path)) return json(route, ok(detailFixture));
    return json(
      route,
      {
        success: false,
        data: null,
        error: {
          code: "E2E_ROUTE_UNHANDLED",
          message: path,
          owner_module: "e2e",
          retryable: false,
          suggested_action: "add route fixture",
        },
        meta: null,
      },
      500,
    );
  });
}
