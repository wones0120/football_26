import { test } from "node:test";
import assert from "node:assert/strict";
import { classicLivePreflightLabel } from "../src/classicLiveReadiness.ts";

test("coverage scores and previews cannot claim live Classic readiness", () => {
  assert.equal(classicLivePreflightLabel(), "Unverified — readiness required");
  assert.equal(classicLivePreflightLabel({ status: "DEVELOPMENT_PREVIEW", score: 100 }), "Unverified — readiness required");
  assert.equal(classicLivePreflightLabel({ status: "NOT_READY", score: 96 }), "Blocked — source refresh required");
  assert.equal(classicLivePreflightLabel({ status: "ERROR" }), "Blocked — evidence check failed");
  assert.equal(classicLivePreflightLabel({ status: "READY" }), "Ready for generation");
});

import { classicLiveReadinessSummary, classicLiveSourceActions } from "../src/classicLiveReadiness.ts";
test("Classic preflight counts required sources and gives recovery actions instead of a misleading coverage score", () => {
  const report = { status: "NOT_READY", required_sources: { market: { status: "READY" }, salary_pool: { status: "NOT_READY" } } };
  assert.equal(classicLiveReadinessSummary(report), "Required sources ready: 1/2. Final entry clearance is separate.");
  assert.deepEqual(classicLiveSourceActions(report), ["Salary: verify the original CSV lineage and resolve identities; a validated file does not need replacement."]);
  assert.equal(classicLiveReadinessSummary(), "Required source assessment unavailable.");
});
