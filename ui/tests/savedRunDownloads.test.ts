import assert from "node:assert/strict";
import test from "node:test";
import { downloadSavedRun, savedDownloadBlocker } from "../src/savedRunDownloads.ts";
import type { OptimizerRunSummary } from "../src/api.ts";
const scope = {season: 2026, week: 6, slate: "THURSDAY_NIGHT", contest_format: "showdown" as const};
const saved: OptimizerRunSummary = {...scope, optimizer_run_id: "clicked-saved-run", objective: "gpp", strategy: "showdown_gpp_portfolio_v3", status: "completed",
  created_at: "2026-10-15T12:00:00Z", updated_at: "2026-10-15T12:00:00Z", started_at: null, completed_at: null, operational_job_id: null,
  requested_lineups: 5, lineup_count: 4, expanded_discovery: null, projection_run_id: "saved-projection", saved_report_available: true,
  entry_ready: true, saved_recommendation_available: true};

test("downloads bind to clicked saved run and mode, including a completed underfill", async () => {
  const calls: unknown[] = [];
  const download = async (id: string, recommended: boolean) => { calls.push([id, recommended]); };
  await downloadSavedRun(saved, scope, "recommended", download);
  await downloadSavedRun(saved, scope, "all", download);
  assert.deepEqual(calls, [["clicked-saved-run", true], ["clicked-saved-run", false]]);
  assert.equal(saved.lineup_count, 4);
});

test("other slate, failed or partial runs, and research clearance cannot download", async () => {
  for (const run of [{...saved, slate: "SUNDAY_MAIN"}, {...saved, status: "failed"}, {...saved, status: "running"},
    {...saved, lineup_count: 0}, {...saved, entry_ready: false}, {...saved, preliminary_export_blocked: true}]) {
    let calls = 0;
    await assert.rejects(downloadSavedRun(run, scope, "all", async () => { calls++; }));
    assert.equal(calls, 0);
  }
  assert.match(savedDownloadBlocker({...saved, entry_ready: false}, scope, "all")!, /not entry cleared/);
});

test("missing recommendation cannot silently pick first lineup or block all saved lineups", () => {
  const missing = {...saved, saved_recommendation_available: false};
  assert.match(savedDownloadBlocker(missing, scope, "recommended")!, /no saved GPP recommendation/);
  assert.equal(savedDownloadBlocker(missing, scope, "all"), null);
  assert.match(savedDownloadBlocker({...saved, objective: "cash"}, scope, "recommended")!, /no saved GPP/);
});

test("server validation errors remain actionable and no alternative run is downloaded", async () => {
  const calls: string[] = [];
  await assert.rejects(downloadSavedRun(saved, scope, "all", async (id) => {
    calls.push(id); throw new Error("Captain is missing a DraftKings Captain ID; regenerate the run");
  }), /DraftKings Captain ID/);
  assert.deepEqual(calls, [saved.optimizer_run_id]);
});

test("provisional upload check is scoped and expires without claiming final clearance", () => {
  const provisional = {...saved, entry_ready: false, upload_ready: true, upload_valid_until: new Date(Date.now()+60_000).toISOString()};
  assert.equal(savedDownloadBlocker(provisional, scope, "all"), null);
  assert.ok(savedDownloadBlocker({...provisional, upload_valid_until: new Date(Date.now()-1).toISOString()}, scope, "all"));
  assert.ok(savedDownloadBlocker({...provisional, preliminary_export_blocked: true}, scope, "all"));
  assert.ok(savedDownloadBlocker({...provisional, slate:"OTHER"}, scope, "all"));
});
