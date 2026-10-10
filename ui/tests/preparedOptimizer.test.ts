import test from "node:test";
import assert from "node:assert/strict";
import { optimizerHasPreparedInputs, optimizerWaitingStatus } from "../src/preparedOptimizer.ts";

const scope = { season: 2026, week: 5, slate: "SUNDAY_MAIN" };
const status: any = { scope, build_current: true, prelock: true, jobs: [], latest_build: {
  ...scope, action: "prepare", contest_format: "classic", data_readiness: { status: "READY" },
  availability_overrides: [{ player_id: null, player_name: "Example", availability: "assume_active" }],
} };
const overrides = [{ availability: "assume_active", player_name: "Example" }];
test("prepared scenario ignores JSON field order and null defaults", () => {
  assert.equal(optimizerHasPreparedInputs(status, scope, "classic", overrides), true);
});
test("source changes, running work, wrong scope/format, old rebuild and changed scenarios block optimization", () => {
  for (const patch of [{ build_current: false }, { prelock: false }, { jobs: [{ status: "running" }] },
    { latest_build: { ...status.latest_build, action: "rebuild" } },
    { latest_build: { ...status.latest_build, data_readiness: { status: "NOT_READY" } } }]) {
    assert.equal(optimizerHasPreparedInputs({ ...status, ...patch }, scope, "classic", overrides), false);
  }
  assert.equal(optimizerHasPreparedInputs(status, { ...scope, week: 6 }, "classic", overrides), false);
  assert.equal(optimizerHasPreparedInputs(status, scope, "showdown", overrides), false);
  assert.equal(optimizerHasPreparedInputs(status, scope, "classic", []), false);
  assert.equal(optimizerHasPreparedInputs(status, scope, "classic", null), false);
});

test("a successful prepare clears older rebuild errors; failed prepare is visible upstream", async () => {
  const { preparationBuildIssue } = await import("../src/showdownPreparation.ts");
  const failed = { job_id: "old", action: "rebuild", status: "failed", stage: "failed", error: "old error" };
  assert.equal(preparationBuildIssue({ ...status, jobs: [{ ...failed, action: "prepare", status: "completed" }, failed] }, scope), null);
  assert.equal(preparationBuildIssue({ ...status, jobs: [{ ...failed, action: "prepare", error: "source unavailable" }] }, scope)?.message,
    "Input preparation failed: source unavailable");
});


test("disabled optimizer explains loading, stale scope, errors, jobs and required preparation", () => {
  const initial = optimizerWaitingStatus(null, scope, false, null, null, null);
  assert.equal(initial.busy, true);
  assert.match(initial.message, /Checking saved slate readiness/);
  assert.equal(optimizerWaitingStatus(status, { ...scope, week: 6 }, false, null, null, null).busy, true);
  const failed = optimizerWaitingStatus(null, scope, false, null, "Request timed out", null);
  assert.equal(failed.busy, false);
  assert.match(failed.message, /Request timed out.*Retrying automatically/);
  assert.match(optimizerWaitingStatus({ ...status, jobs: [{ status: "running", message: "Checking player identities" }] },
    scope, false, null, null, null).message, /Checking player identities/);
  assert.match(optimizerWaitingStatus({ ...status, build_issue: "Source inputs changed" }, scope, false, null, null, null).message, /Source inputs changed/);
  assert.match(optimizerWaitingStatus(status, scope, false, null, null, null).message, /Preparation required/);
  assert.match(optimizerWaitingStatus({ ...status, prelock: false }, scope, false, null, null, null).message, /slate has locked/);
  assert.equal(optimizerWaitingStatus(status, scope, false, null, null, "Invalid assumption").message, "Invalid assumption");
});
test("ready and other pending operations stay distinct", () => {
  assert.deepEqual(optimizerWaitingStatus(status, scope, true, null, null, null), {
    busy: false, message: "Ready to optimize — prepared inputs verified." });
  assert.deepEqual(optimizerWaitingStatus(status, scope, true, "Refreshing readiness and optimizer status...", null, null), {
    busy: true, message: "Refreshing readiness and optimizer status..." });
});
