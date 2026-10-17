// Real App -> real API -> durable fixture worker -> SQLite lineage. All external
// traffic is blocked. Source/model I/O is synthetic; no application data is used.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { readFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const artifacts = root + "artifacts/sunday_night_auto_preparation/ui_fixture"; mkdirSync(artifacts, { recursive: true });
const appServer = createServer((req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  const file = resolve(root, "ui/dist", "." + (path === "/" ? "/index.html" : path));
  if (!file.startsWith(resolve(root, "ui/dist") + "/")) return res.writeHead(403).end();
  try { res.setHeader("content-type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html"); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => appServer.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${appServer.address().port}`;
const portServer = createServer(); await new Promise(r => portServer.listen(0, "127.0.0.1", r));
const port = portServer.address().port; await new Promise(r => portServer.close(r));
const api = `http://127.0.0.1:${port}`;
const worker = spawn(root + ".venv/bin/python", ["backend/app/tests/product/slate_preparation_fixture.py", String(port)], { cwd: root, env: { ...process.env, PYTHONPATH: root } });
let logs = ""; worker.stderr.on("data", bytes => { logs += bytes; });
let browser;
try {
  for (let i = 0; ; i++) {
    try { if ((await fetch(api + "/openapi.json")).ok) break; } catch { /* fixture starting */ }
    assert.ok(i < 300, logs); await new Promise(r => setTimeout(r, 100));
  }
  browser = await chromium.launch({ headless: true, channel: "chrome" });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: "block" });
  const page = await context.newPage(); const errors = []; const writes = [];
  page.on("pageerror", e => { errors.push(e.message); console.error("Browser error:", e.message); });
  const readiness = { status: "pass", score: 100, summary: { pass: 1, warn: 0, fail: 0 }, checks: [], gates: Object.fromEntries(["prediction", "classic_gpp", "classic_cash", "showdown_gpp", "showdown_cash"].map(k => [k, { status: "pass", score: 100, summary: { pass: 1, warn: 0, fail: 0 }, blocking_checks: [], attention_checks: [], message: "Synthetic ready" }])) };
  await context.route("**/*", route => {
    if (new URL(route.request().url()).origin !== base || route.request().method() !== "GET") return route.abort();
    return route.continue();
  });
  let optimizerPayload;
  await context.route("**/api/**", async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname.replace(/^\/api/, "");
    const reply = (json, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
    if (req.method() !== "GET") writes.push({ path, body: req.postDataJSON() });
    if (path === "/meta/current") return reply({ season: 2000, week: 1, slate: "SUNDAY_MAIN" });
    if (path === "/slate/readiness") return reply(readiness);
    if (path === "/slate/identity-reconcile") return reply({ salary_rows_seen: 1, salary_rows_resolved: 0, salary_rows_quarantined: 1 });
    if (path === "/ownership/run") return reply({ rows_written: 1, ownership_run_id: "fixture-own" });
    if (path === "/optimizer/projections") return reply({ runs: [] });
    if (path === "/optimizer/runs") return reply({ runs: [] });
    if (path === "/weekly/runs") return reply({ rows: [] });
    if (path === "/weekly-runs") return reply({ detail: "Fixture weekly request captured" }, 422);
    if (path === "/slate/preparation" || path === "/slate/preparation/jobs" || path === "/jobs" || path.startsWith("/jobs/") || path === "/optimizer/jobs") {
      const idempotency = await req.headerValue("idempotency-key");
      const response = await fetch(api + url.pathname + url.search, { method: req.method(),
        headers: { "content-type": "application/json", ...(idempotency ? { "Idempotency-Key": idempotency } : {}) },
        ...(req.method() !== "GET" ? { body: req.postData() } : {}) });
      const result = await response.json();
      if (path === "/optimizer/jobs") {
        assert.equal(response.status, 202, JSON.stringify(result)); optimizerPayload = req.postDataJSON();
        return reply({ detail: "Fixture request validated and queued; solver intentionally not executed" }, 422);
      }
      return reply(result, response.status);
    }
    return reply({ detail: "Unavailable in isolated fixture" }, 503);
  });
  await page.addInitScript(() => { localStorage.setItem("football-26-active-slate-context", JSON.stringify({ season: 2000, week: 1, slate: "SUNDAY_MAIN" })); });
  await page.goto(base); await page.getByRole("button", { name: "Operations", exact: true }).click();
  assert.equal(await page.getByTestId("preparation-tools").getAttribute("open"), null);
  assert.equal(await page.getByTestId("weekly-pipeline-options").getAttribute("open"), null);
  assert.equal(await page.getByTestId("optimizer-options").getByRole("heading", { name: "Optimizer options" }).isVisible(), true);
  assert.equal(await page.getByLabel("No QB Captain", { exact: true }).count(), 0);
  await page.getByTestId("preparation-tools").locator(":scope > summary").click();
  assert.equal(await page.getByLabel("Exclude questionable (Q) players").isChecked(), true, "Classic defaults to excluding Q");
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Format/ }).selectOption("showdown");
  assert.equal(await page.getByLabel("Exclude questionable (Q) players").isChecked(), true, "Showdown defaults to excluding Q");
  await page.getByLabel("Exclude questionable (Q) players").uncheck();
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Format/ }).selectOption("classic");
  assert.equal(await page.getByLabel("Exclude questionable (Q) players").isChecked(), true);
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Format/ }).selectOption("showdown");
  assert.equal(await page.getByLabel("Exclude questionable (Q) players").isChecked(), false, "Explicit choice survives format switching");
  await page.getByLabel("Exclude questionable (Q) players").check();
  const decisions = page.getByRole("region", { name: "Player availability and lineup preferences" });
  await decisions.locator("input[type=text]").first().fill("Preference Receiver");
  await decisions.getByLabel("Exclude from lineups", { exact: true }).check();
  await page.getByLabel("Exclude from Captain (FLEX still allowed; comma-separated names)").fill("Synthetic TE");
  await page.getByLabel("Hard exclude players facing teams (comma-separated codes)").fill("DEN");
  assert.equal(await page.getByLabel("No QB Captain", { exact: true }).isChecked(), false);
  assert.equal(await page.getByLabel("No 2 QBs in the lineup", { exact: true }).isChecked(), false);
  await page.getByLabel("No QB Captain", { exact: true }).check();
  await page.getByLabel("No 2 QBs in the lineup", { exact: true }).check();
  const prep = page.getByTestId("slate-preparation");
  await prep.getByRole("button", { name: "Refresh sportsbook lines", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("markets: queued"));
  assert.equal(await prep.getByRole("button", { name: "Rebuild slate features and projections" }).isDisabled(), true);
  let result = await (await fetch(api + "/fixture/work", { method: "POST" })).json();
  assert.equal(result.status, "completed", JSON.stringify(result));
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("markets: completed"));
  assert.equal(await page.getByLabel("Exclude questionable (Q) players").isChecked(), true);
  assert.equal(await decisions.getByLabel("Exclude from lineups", { exact: true }).isChecked(), true);
  const beforeBuild = await (await fetch(api + "/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN")).json();
  assert.equal(beforeBuild.latest_build, null);
  await page.getByLabel("Refresh ownership before optimizing").uncheck();
  await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("rebuild: queued"));
  assert.equal(await page.getByRole("button", { name: "Run Optimizer", exact: true }).isDisabled(), true);
  assert.equal(optimizerPayload, undefined, "Optimizer must wait for verified preparation");
  result = await (await fetch(api + "/fixture/work", { method: "POST" })).json();
  assert.equal(result.status, "completed", JSON.stringify(result));
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("Verified current prepared projection"));
  const snapshot = await (await fetch(api + "/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN")).json();
  assert.deepEqual(snapshot.latest_build.consumption.market_snapshot_ids, ["synthetic-market-2"]);
  assert.equal(snapshot.entry_ready, false);
  await page.waitForFunction(() => document.body.textContent.includes("Fixture request validated and queued"));
  assert.equal(optimizerPayload.projection_run_id, snapshot.latest_build.projection_run_id);
  assert.equal(optimizerPayload.params.prepared_input_job_id, snapshot.latest_build.prepared_input_job_id);
  assert.equal(optimizerPayload.params.num_lineups, 5);
  assert.equal(optimizerPayload.params.max_exposure, .6);
  assert.equal(optimizerPayload.strategy, "showdown_gpp_portfolio_v3");
  assert.equal(optimizerPayload.contest_format, "showdown");
  assert.equal(optimizerPayload.params.exclude_questionable, true);
  assert.equal(optimizerPayload.params.exclusions_assumed_out, false);
  assert.deepEqual(optimizerPayload.params.availability_overrides, []);
  assert.deepEqual(optimizerPayload.params.exclude_players, ["Preference Receiver"]);
  assert.deepEqual(optimizerPayload.params.flex_only_players, ["Synthetic TE"]);
  assert.deepEqual(optimizerPayload.params.exclude_opponent_teams, ["DEN"]);
  assert.equal(optimizerPayload.params.enforce_single_te, false);
  assert.equal(optimizerPayload.params.no_qb_captain, true);
  assert.equal(optimizerPayload.params.no_two_qbs, true);
  assert.equal(optimizerPayload.params.max_lineups_per_primary_game, undefined);
  assert.equal(optimizerPayload.params.max_lineup_overlap, undefined);
  assert.ok(writes.filter(r => r.path === "/slate/preparation/jobs").every(r =>
    r.body.assume_questionable_out === false && r.body.availability_overrides.length === 0));
  assert.equal(writes.filter(r => r.path === "/slate/preparation/jobs").length, 2);
  assert.equal(writes.filter(r => r.path === "/predict/run" || r.path === "/features/matrix/build").length, 0);
  const reconcileIndex = writes.findIndex(r => r.path === "/slate/identity-reconcile");
  assert.ok(reconcileIndex >= 0);
  assert.deepEqual(writes[reconcileIndex].body, { season: 2000, week: 1, slate: "SUNDAY_MAIN" });
  const automaticBuildIndex = writes.findIndex((r, i) => i > reconcileIndex && r.path === "/slate/preparation/jobs" && r.body.action === "rebuild");
  assert.ok(automaticBuildIndex > reconcileIndex, "Identity reconciliation must precede the automatic prepared source snapshot");
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Objective/ }).selectOption("cash");
  assert.equal(await page.getByLabel("No QB Captain", { exact: true }).isVisible(), true);
  assert.equal(await page.getByLabel("No 2 QBs in the lineup", { exact: true }).isChecked(), true);
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Objective/ }).selectOption("gpp");
  await page.getByLabel("Showdown QB lineup preferences", { exact: true }).screenshot({ path: artifacts + "/qb-preferences-desktop.png" });
  await page.getByTestId("weekly-pipeline-options").locator(":scope > summary").click();
  await page.getByLabel(/^DraftKings directory/).fill("/synthetic/NFL");
  await page.getByRole("button", { name: "Run Weekly Pipeline", exact: true }).click();
  await page.getByText(/Fixture weekly request captured/).waitFor();
  const weeklyPayload = writes.find(row => row.path === "/weekly-runs").body;
  assert.equal(weeklyPayload.optimizer_params.no_qb_captain, true);
  assert.equal(weeklyPayload.optimizer_params.no_two_qbs, true);
  await page.getByTestId("weekly-pipeline-options").locator(":scope > summary").click();
  await prep.screenshot({ path: artifacts + "/preparation-desktop.png" });
  await page.locator(".operations-projection-status").screenshot({ path: artifacts + "/optimizer-status-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Showdown QB lineup preferences", { exact: true }).screenshot({ path: artifacts + "/qb-preferences-mobile.png" });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Showdown options must fit mobile width");
  await prep.screenshot({ path: artifacts + "/preparation-mobile.png" });
  await page.locator(".operations-projection-status").screenshot({ path: artifacts + "/optimizer-status-mobile.png" });
  assert.deepEqual(errors, []);
  console.log("PASS: Run Optimizer automatically builds and verifies missing Showdown preparation through the real UI/API/queue/worker, then sends the pinned optimizer request. Exclusion-only scenario and FLEX-only/preferences preserved. Synthetic source/model adapters; no live source or solver.");
} finally {
  await browser?.close(); worker.kill("SIGTERM"); await new Promise(r => appServer.close(r));
}
