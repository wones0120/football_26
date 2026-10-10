import assert from "node:assert/strict";
import test from "node:test";
import type { PreparationStatus, PreparedBuild } from "../src/api.ts";
import { prepareShowdownForOptimizer, prepareSlateForOptimizer, preparationBuildIssue } from "../src/showdownPreparation.ts";

const scope = { season: 2000, week: 1, slate: "SUNDAY_NIGHT" };
const build: PreparedBuild = { ...scope, prepared_input_job_id: "new-build", projection_run_id: "new-projection",
  feature_run_id: "new-feature", source_sha256: "verified-source", consumption: {}, limitations: [] };
const status = (changes: Partial<PreparationStatus> = {}): PreparationStatus => ({
  scope, server_time: "2000-01-01T00:00:00Z", inputs: {}, jobs: [], prelock: true,
  latest_build: null, build_current: false, limitations: [], entry_ready: false, ...changes,
});
function fixture(states: PreparationStatus[]) {
  const calls: Array<{ action: string; value?: unknown }> = [];
  let queueError: string | null = null;
  let waitError: string | null = null;
  const actions = {
    status: async (target: typeof scope) => { calls.push({ action: "status", value: target }); return states.shift()!; },
    reconcile: async (target: typeof scope) => { calls.push({ action: "reconcile", value: target }); },
    queue: async (request: unknown) => {
      calls.push({ action: "queue", value: request });
      if (queueError) throw new Error(queueError);
      return { job: { job_id: "new-build" } };
    },
    wait: async (id: string) => { calls.push({ action: "wait", value: id }); if (waitError) throw new Error(waitError); },
    progress: (message: string) => { calls.push({ action: "progress", value: message }); },
  };
  return { actions, calls, failQueue: (message: string) => { queueError = message; },
    failWait: (message: string) => { waitError = message; } };
}
const ready = () => status({ latest_build: build, build_current: true });

test("preflight retains the latest failed rebuild while newer rebuilds show preparation in progress", () => {
  const failed = { job_id: "failed-build", action: "rebuild", status: "failed", stage: "failed", error: "Invalid availability override" };
  assert.match(preparationBuildIssue(status({ jobs: [failed] }), scope)!.message, /Input preparation failed.*Invalid availability override/);
  assert.match(preparationBuildIssue(status({ jobs: [{ ...failed, action: "injuries", status: "completed" }, failed] }), scope)!.message, /Invalid availability override/);
  for (const newerStatus of ["queued", "running"]) {
    assert.equal(preparationBuildIssue(status({ jobs: [{ ...failed, status: newerStatus }, failed] }), scope)?.status, "preparing");
  }
  assert.equal(preparationBuildIssue(status({ jobs: [{ ...failed, status: "completed" }, failed] }), scope), null);
  assert.equal(preparationBuildIssue(status({ jobs: [failed] }), { ...scope, week: 2 }), null);
  assert.equal(preparationBuildIssue(status({ jobs: [failed] }), { ...scope, slate: "SUNDAY_MAIN" }), null);
  assert.equal(preparationBuildIssue(null, scope), null);
  assert.equal(preparationBuildIssue(ready(), scope), null);
});

test("missing preparation builds before returning the exact verified projection", async () => {
  const f = fixture([status(), ready()]);
  const result = await prepareShowdownForOptimizer(scope, [], f.actions);
  assert.equal(result, build);
  assert.deepEqual(f.calls.filter(c => c.action !== "progress").map(c => c.action), ["status", "reconcile", "queue", "wait", "status"]);
  assert.deepEqual(f.calls.find(c => c.action === "queue")?.value, { ...scope, action: "rebuild", availability_overrides: [], assume_questionable_out: false });
});

test("a latest completed assumed-out build cannot substitute for the selected scenario", async () => {
  const old = { ...build, prepared_input_job_id: "old-assumed-out", projection_run_id: "old-projection" };
  const f = fixture([status({ latest_build: old, build_current: true }), ready()]);
  const overrides = [{ player_id: "explicit-scenario-player", availability: "assume_active" as const }];
  const result = await prepareShowdownForOptimizer(scope, overrides, f.actions);
  assert.equal(result.projection_run_id, "new-projection");
  const payload = f.calls.find(c => c.action === "queue")!.value as { availability_overrides: unknown[] };
  assert.deepEqual(payload.availability_overrides, overrides);
  assert.notEqual(payload.availability_overrides, overrides);
});

test("an existing source import is awaited before checking identity and building", async () => {
  const active = status({ prelock: undefined, jobs: [{ job_id: "salary-import", action: "salary", status: "running", stage: "import" }] });
  const f = fixture([active, status(), ready()]);
  await prepareShowdownForOptimizer(scope, [], f.actions);
  assert.deepEqual(f.calls.filter(c => c.action === "wait").map(c => c.value), ["salary-import", "new-build"]);
});

test("missing game identity and passed lock still prevent any build", async () => {
  for (const state of [status({ prelock: undefined, limitations: ["Load canonical schedule evidence"] }), status({ prelock: false, lock_at: "2000-01-01T00:00:00Z" })]) {
    const f = fixture([state]);
    await assert.rejects(prepareShowdownForOptimizer(scope, [], f.actions), /schedule evidence|locked at/);
    assert.equal(f.calls.some(c => c.action === "queue"), false);
  }
});

test("a failed build stops the optimizer flow with the original failure", async () => {
  const f = fixture([status()]); f.failWait("New market evidence was not consumed");
  await assert.rejects(prepareShowdownForOptimizer(scope, [], f.actions), /market evidence was not consumed/);
  assert.equal(f.calls.filter(c => c.action === "status").length, 1);
});

test("an enqueue rejection stops before waiting or consuming any projection", async () => {
  const f = fixture([status()]); f.failQueue("Preparation request rejected");
  await assert.rejects(prepareShowdownForOptimizer(scope, [], f.actions), /request rejected/);
  assert.equal(f.calls.some(c => c.action === "wait"), false);
});

test("availability choices are frozen while preparation awaits its status", async () => {
  const overrides = [{ player_id: "explicit-player", availability: "assume_out" as const }];
  const f = fixture([status(), ready()]);
  const originalStatus = f.actions.status;
  f.actions.status = async target => { overrides.length = 0; return originalStatus(target); };
  await prepareShowdownForOptimizer(scope, overrides, f.actions);
  assert.deepEqual((f.calls.find(c => c.action === "queue")!.value as { availability_overrides: unknown[] }).availability_overrides,
    [{ player_id: "explicit-player", availability: "assume_out" }]);
});

test("changed sources, another build, incomplete lineage, or lock after build cannot be consumed", async () => {
  const invalid = [status({ latest_build: build, build_current: false }),
    status({ latest_build: { ...build, prepared_input_job_id: "other-build" }, build_current: true }),
    status({ latest_build: { ...build, projection_run_id: "" }, build_current: true }),
    status({ latest_build: build, build_current: true, prelock: false, lock_at: "2000-01-01T00:00:00Z" }),
    status({ latest_build: build, build_current: true, scope: { ...scope, week: 2 } })];
  for (const final of invalid) {
    const f = fixture([status(), final]);
    await assert.rejects(prepareShowdownForOptimizer(scope, [], f.actions), /superseded|lineage is incomplete|locked at|another slate/);
  }
});

test("Classic Run Optimizer rebuilds with current Q and explicit availability choices", async () => {
  for (const excludeQuestionable of [true, false]) {
    const f = fixture([ready(), ready()]);
    const overrides = [{ player_id: "classic-player", availability: "assume_out" as const }];
    const result = await prepareSlateForOptimizer(scope, overrides, f.actions,
      { label: "Classic", assumeQuestionableOut: excludeQuestionable });
    assert.equal(result, build);
    assert.deepEqual(f.calls.find(c => c.action === "queue")?.value,
      { ...scope, action: "rebuild", availability_overrides: overrides, assume_questionable_out: excludeQuestionable });
  }
});

test("Classic preparation rejects a superseded build before optimizer submission", async () => {
  const f = fixture([status(), status({ build_current: true,
    latest_build: { ...build, prepared_input_job_id: "old-scenario" } })]);
  await assert.rejects(prepareSlateForOptimizer(scope, [], f.actions,
    { label: "Classic", assumeQuestionableOut: true }), /Classic preparation was superseded/);
});


test("salary reconciliation is scoped and finishes before any prepared source snapshot", async () => {
  const f = fixture([status(), ready()]);
  await prepareShowdownForOptimizer(scope, [], f.actions);
  const reconcile = f.calls.findIndex(c => c.action === "reconcile");
  assert.deepEqual(f.calls[reconcile].value, scope);
  assert.ok(reconcile < f.calls.findIndex(c => c.action === "queue"));
});

test("failed identity reconciliation cannot enqueue a build or return an old projection", async () => {
  const f = fixture([ready()]);
  f.actions.reconcile = async () => { throw new Error("Identity review is unavailable"); };
  await assert.rejects(prepareShowdownForOptimizer(scope, [], f.actions), /Identity review is unavailable/);
  assert.equal(f.calls.some(c => c.action === "queue" || c.action === "wait"), false);
});
