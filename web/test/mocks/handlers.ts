import { http, HttpResponse } from "msw";
import { detailFixture, jobsFixture, ok, planFixture, reportFixture } from "../fixtures";

const apiBase = "http://127.0.0.1:8765/api/v0";

export const handlers = [
  http.get(`${apiBase}/healthz`, () => HttpResponse.json(ok({ version: "test", engines: { miu2d: true } }))),
  http.get(`${apiBase}/jobs`, () => HttpResponse.json(ok(jobsFixture))),
  http.get(`${apiBase}/jobs/:id`, () => HttpResponse.json(ok(detailFixture))),
  http.get(`${apiBase}/jobs/:id/plan`, () => HttpResponse.json(ok(planFixture))),
  http.get(`${apiBase}/jobs/:id/report`, () => HttpResponse.json(ok(reportFixture))),
];
