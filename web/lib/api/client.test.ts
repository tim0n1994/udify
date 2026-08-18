import { http, HttpResponse } from "msw";
import { api } from "./client";
import { server } from "@/test/mocks/server";
import { jobsFixture, ok } from "@/test/fixtures";

const jobsUrl = "http://127.0.0.1:8765/api/v0/jobs";

describe("runtime API decoding", () => {
  it("decodes a successful envelope through Zod", async () => {
    await expect(api.listJobs()).resolves.toEqual(jobsFixture);
  });

  it("surfaces ErrorRecord from an error envelope", async () => {
    server.use(
      http.get(jobsUrl, () =>
        HttpResponse.json(
          {
            success: false,
            data: null,
            error: {
              code: "JOB_QUERY_FAILED",
              message: "boom",
              owner_module: "api",
              retryable: true,
              suggested_action: "retry",
            },
            meta: null,
          },
          { status: 500 },
        ),
      ),
    );
    await expect(api.listJobs()).rejects.toMatchObject({
      record: { code: "JOB_QUERY_FAILED", retryable: true },
      status: 500,
    });
  });

  it("rejects a success envelope with malformed job data", async () => {
    server.use(http.get(jobsUrl, () => HttpResponse.json(ok([{ status: null }]))));
    await expect(api.listJobs()).rejects.toMatchObject({
      record: { code: "API_RESPONSE_INVALID" },
    });
  });
});
