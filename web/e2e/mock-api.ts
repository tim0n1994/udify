import type { Page, Route } from "@playwright/test";
import { detailFixture, jobsFixture, ok, planFixture, reportFixture } from "@/test/fixtures";

export interface MockApiAudit {
  offline: boolean;
  intercepted: string[];
  unhandled: string[];
}

function json(route: Route, data: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
}

export async function installMockApi(page: Page): Promise<MockApiAudit> {
  const audit: MockApiAudit = { offline: false, intercepted: [], unhandled: [] };
  await page.context().route((url) => url.pathname === "/api" || url.pathname.startsWith("/api/"), async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    audit.intercepted.push(`${request.method()} ${url.href}`);
    if (audit.offline) return route.abort("connectionrefused");
    if (path.endsWith("/healthz")) return json(route, ok({ version: "e2e", engines: { miu2d: true } }));
    if (path === "/api/v0/jobs" && request.method() === "GET") return json(route, ok(jobsFixture));
    if (path.endsWith("/events")) {
      return route.fulfill({ status: 200, contentType: "text/event-stream", body: "retry: 2000\n\n: mock observation\n\n" });
    }
    if (path.endsWith("/plan")) return json(route, ok(planFixture));
    if (path.endsWith("/report")) return json(route, ok(reportFixture));
    if (path.endsWith("/approve") && request.method() === "POST") {
      return json(route, ok({ ...detailFixture.job, status: "applying" }));
    }
    if (path.endsWith("/reject") && request.method() === "POST") {
      return json(route, ok({ ...detailFixture.job, status: "rejected" }));
    }
    if (/\/api\/v0\/jobs\/[^/]+$/.test(path)) return json(route, ok(detailFixture));
    audit.unhandled.push(`${request.method()} ${url.href}`);
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
  return audit;
}
