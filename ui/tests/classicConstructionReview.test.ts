import assert from "node:assert/strict";
import test from "node:test";
import { ConstructionReviewError, requestConstructionReview } from "../src/classicConstructionReview.ts";

test("Review sends only the explicit diagnostic with one-based entry and false preserved", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const fetcher = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ status: "completed", comparisons: [{ family: "RB FLEX" }] }));
  }) as typeof fetch;
  const report = await requestConstructionReview("/api", "saved/id", 1, false, fetcher);
  assert.equal(report.comparisons[0].family, "RB FLEX");
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/optimizer/results/saved%2Fid/construction-review?entry=1&enforce_single_te=false");
  assert.equal(requests[0].init?.method, "POST");
  assert.equal(requests[0].init?.body, "{}");
});

for (const [status, detail, code] of [
  [404, "Not Found", "endpoint_unavailable"],
  [404, { code: "saved_run_not_found", request_id: "trace-1" }, "saved_run_not_found"],
  [422, { code: "frozen_inputs_missing" }, "frozen_inputs_missing"],
  [422, { code: "incompatible_contract" }, "incompatible_contract"],
  [422, { code: "invalid_entry" }, "invalid_entry"],
  [500, { code: "calculation_failure" }, "calculation_failure"],
] as const) test(`HTTP ${status} distinguishes ${code}`, async () => {
  const fetcher = (async () => new Response(JSON.stringify({ detail }), { status })) as typeof fetch;
  await assert.rejects(requestConstructionReview("/api", "saved-job", 1, false, fetcher), (error: unknown) => {
    assert.ok(error instanceof ConstructionReviewError);
    assert.equal(error.code, code);
    assert.ok(error.nextAction.length > 0);
    assert.match(error.technical, /saved-job/);
    assert.match(error.technical, new RegExp(`HTTP ${status}`));
    assert.doesNotMatch(error.message, /infeasible|competitive/);
    if (typeof detail === "object" && "request_id" in detail) assert.match(error.technical, /trace-1/);
    return true;
  });
});

test("An unavailable or empty HTTP 200 is never a successful construction review", async () => {
  for (const body of [{ status: "unavailable", code: "frozen_inputs_missing" }, {}, { status: "completed", comparisons: [] }]) {
    const fetcher = (async () => new Response(JSON.stringify(body))) as typeof fetch;
    await assert.rejects(requestConstructionReview("/api", "saved-job", 1, true, fetcher), ConstructionReviewError);
  }
});
