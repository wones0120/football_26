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
const artifacts = root + "artifacts/basic_optimizer_workflow"; mkdirSync(artifacts, { recursive: true });
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
  let releaseSalary;
  let automaticallyWork = false;
  let identitiesReconciled = false;
  await context.route("**/api/**", async route => {
    const req = route.request(); const url = new URL(req.url()); const path = url.pathname.replace(/^\/api/, "");
    const reply = (json, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
    if (req.method() !== "GET") writes.push({ path, body: req.postDataJSON() });
    if (path === "/ingest/salaries") {
      await new Promise(resolve => { releaseSalary = resolve; });
      return reply({ rows_raw: 1, rows_curated: 1, rows_unresolved: 0 });
    }
    if (path === "/ingest/injuries") return reply({ rows_raw: 1, rows_curated: 1, rows_unresolved: 0 });
    if (path === "/meta/current") return reply({ season: 2000, week: 1, slate: "SUNDAY_MAIN" });
    if (path === "/slate/readiness") {
      if (identitiesReconciled) return reply({ ...readiness,
        checks: [{ check_id: "player_identity_coverage", status: "warn", message: "Unmatched salary excluded for identity review." }],
        gates: Object.fromEntries(Object.entries(readiness.gates).map(([key, gate]) => [key, { ...gate,
          status: "warn", attention_checks: ["player_identity_coverage"], message: "Ready with identity review warning." }])) });
      return reply({ ...readiness, checks: [{ check_id: "player_identity_coverage", status: "fail", message: "1 unresolved salary is not quarantined." }],
        gates: Object.fromEntries(Object.entries(readiness.gates).map(([key, gate]) => [key, { ...gate,
          status: "fail", blocking_checks: ["player_identity_coverage"], attention_checks: ["player_identity_coverage"], message: "Blocked by identity reconciliation." }])) });
    }
    if (path === "/slate/identity-reconcile") {
      identitiesReconciled = true;
      return reply({ salary_rows_seen: 1, salary_rows_resolved: 0, salary_rows_quarantined: 1 });
    }
    if (path === "/ownership/run") return reply({ rows_written: 1, ownership_run_id: "fixture-own" });
    if (path === "/optimizer/projections") return reply({ runs: [] });
    if (path === "/optimizer/runs") return reply({ runs: [] });
    if (path === "/weekly/runs") return reply({ rows: [] });
    if (path === "/slate/preparation" || path === "/slate/preparation/jobs" || path === "/jobs" || path.startsWith("/jobs/") || path === "/optimizer/jobs") {
      if (automaticallyWork && path.startsWith("/jobs/")) {
        const work = await (await fetch(api + "/fixture/work", { method: "POST" })).json();
        assert.equal(work.status, "completed", JSON.stringify(work));
      }
      const idempotency = await req.headerValue("idempotency-key");
      const response = await fetch(api + url.pathname + url.search, { method: req.method(),
        headers: { "content-type": "application/json", ...(idempotency ? { "Idempotency-Key": idempotency } : {}) },
        ...(req.method() !== "GET" ? { body: req.postData() } : {}) });
      const result = await response.json();
      if (path === "/slate/preparation") {
        // Synthetic unresolved identity display; the real worker's source/model
        // adapters remain isolated and source-to-projection proof runs normally.
        result.inputs.salaries = [{ ...result.inputs.salaries[0], player_master_id: null,
          player_name: "Synthetic unmatched player", team: "BUF", position: "TE" }];
      }
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
  const options = page.getByTestId("optimizer-options");
  const tools = page.getByTestId("preparation-tools");
  assert.equal(await options.getByRole("heading", { name: "Optimizer options" }).isVisible(), true);
  assert.equal(await page.getByRole("button", { name: "Open Model", exact: true }).isVisible(), false);
  assert.equal(await tools.getAttribute("open"), null);
  assert.equal(await page.getByRole("button", { name: "Run Optimizer", exact: true }).isVisible(), true);
  await page.getByText("Salary rows: 1 · Injury rows: 0", { exact: true }).waitFor();
  await page.getByLabel("Salary file", { exact: true }).fill("/synthetic/DKSalaries.csv");
  await page.getByRole("button", { name: "Load salary CSV", exact: true }).click();
  await page.waitForFunction(() => document.body.textContent.includes("Loading salary CSV..."));
  assert.equal(await page.getByRole("button", { name: "Load injury CSV", exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole("button", { name: "Run Optimizer", exact: true }).isDisabled(), true);
  while (!releaseSalary) await new Promise(r => setTimeout(r, 10));
  releaseSalary();
  await page.getByText(/Salaries week 1.*loaded/).waitFor();
  await page.getByLabel("Injury file", { exact: true }).fill("/synthetic/FanDuel_injuries.csv");
  await page.getByRole("button", { name: "Load injury CSV", exact: true }).click();
  await page.getByText(/Injuries week 1.*loaded/).waitFor();
  assert.deepEqual(writes.find(r => r.path === "/ingest/salaries").body,
    { source_system: "draftkings", season: 2000, week: 1, slate: "SUNDAY_MAIN", path: "/synthetic/DKSalaries.csv" });
  assert.deepEqual(writes.find(r => r.path === "/ingest/injuries").body,
    { source_system: "fanduel", season: 2000, week: 1, slate: "SUNDAY_MAIN", path: "/synthetic/FanDuel_injuries.csv" });
  await page.getByLabel(/^Contest Strategy/).selectOption("classic_large_gpp_v1");
  const panel = page.locator(".classic-large-portfolio-controls");
  await panel.getByLabel("Number of lineups", { exact: true }).fill("5");
  await panel.getByLabel("Max player exposure (%)", { exact: true }).fill("80");
  await panel.getByLabel(/^Max lineups per primary game/).selectOption("3");
  await panel.getByLabel(/^Max shared players/).selectOption("5");
  await page.getByLabel("Max players / team").fill("4"); // Must remain 4 until user changes it.
  await page.getByLabel(/Enforce single TE/).uncheck();
  await page.getByLabel("Hard exclude players facing teams (comma-separated codes)").fill("DEN");
  await page.getByLabel("Lock canonical player IDs (advanced)").fill("synthetic-player");
  await tools.locator(":scope > summary").click();
  const prep = page.getByTestId("slate-preparation");
  await prep.getByRole("button", { name: "Refresh sportsbook lines", exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("markets: queued"));
  assert.equal(await prep.getByRole("button", { name: "Rebuild slate features and projections" }).isDisabled(), true);
  // Controls can be edited while preparation runs; callbacks must not replace them.
  await page.getByLabel("Max players / team").fill("4");
  let result = await (await fetch(api + "/fixture/work", { method: "POST" })).json();
  assert.equal(result.status, "completed", JSON.stringify(result));
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("markets: completed"));
  assert.equal(await page.getByLabel("Max players / team").inputValue(), "4");
  assert.equal(await page.getByLabel("Lock canonical player IDs (advanced)").inputValue(), "synthetic-player");
  assert.equal(await page.getByLabel("Hard exclude players facing teams (comma-separated codes)").inputValue(), "DEN");
  assert.equal(await page.getByLabel(/Enforce single TE/).isChecked(), false);
  await prep.getByRole("button", { name: "Rebuild slate features and projections" }).click();
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("rebuild: queued"));
  result = await (await fetch(api + "/fixture/work", { method: "POST" })).json();
  assert.equal(result.status, "completed", JSON.stringify(result));
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("Verified current prepared projection"));
  const snapshot = await (await fetch(api + "/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN")).json();
  assert.deepEqual(snapshot.latest_build.consumption.market_snapshot_ids, ["synthetic-market-2"]);
  assert.equal(snapshot.entry_ready, false);
  await page.reload(); await page.getByRole("button", { name: "Operations", exact: true }).click();
  await tools.locator(":scope > summary").click();
  await page.waitForFunction(() => document.querySelector('[data-testid="slate-preparation"]')?.textContent?.includes("Verified current prepared projection"));
  assert.equal(await panel.getByLabel(/^Max shared players/).inputValue(), "5");
  assert.equal(await panel.getByLabel("Number of lineups", { exact: true }).inputValue(), "5");
  // User makes the requested planning change; preparation never supplies it.
  await page.getByLabel("Max players / team").fill("3");
  await page.getByLabel("Hard exclude players facing teams (comma-separated codes)").fill("DEN");
  await page.getByLabel(/Enforce single TE/).uncheck();
  await page.getByLabel("Refresh ownership before optimizing").uncheck();
  await page.getByLabel("Lock canonical player IDs (advanced)").fill("synthetic-player");
  // Closing preparation tools preserves visible optimizer controls and their request values.
  await tools.locator(":scope > summary").click();
  assert.equal(await panel.isVisible(), true);
  automaticallyWork = true;
  await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
  await page.waitForFunction(() => document.body.textContent.includes("Fixture request validated and queued"));
  const rebuilt = await (await fetch(api + "/api/slate/preparation?season=2000&week=1&slate=SUNDAY_MAIN")).json();
  assert.notEqual(rebuilt.latest_build.prepared_input_job_id, snapshot.latest_build.prepared_input_job_id);
  assert.equal(optimizerPayload.projection_run_id, rebuilt.latest_build.projection_run_id);
  assert.equal(optimizerPayload.params.prepared_input_job_id, rebuilt.latest_build.prepared_input_job_id);
  assert.equal(optimizerPayload.params.num_lineups, 5);
  assert.equal(optimizerPayload.params.max_exposure, .8);
  assert.equal(optimizerPayload.params.max_players_per_team, 3);
  assert.equal(optimizerPayload.params.max_players_per_game, 5);
  assert.equal(optimizerPayload.params.max_lineups_per_primary_game, 3);
  assert.equal(optimizerPayload.params.max_lineup_overlap, 5);
  assert.equal(optimizerPayload.params.enforce_single_te, false);
  assert.deepEqual(optimizerPayload.params.exclude_opponent_teams, ["DEN"]);
  assert.deepEqual(optimizerPayload.params.locked_player_ids, ["synthetic-player"]);
  assert.equal(writes.filter(r => r.path === "/slate/preparation/jobs").length, 3);
  assert.equal(writes.filter(r => r.path === "/predict/run" || r.path === "/features/matrix/build").length, 0);
  const reconcileIndex = writes.findIndex(r => r.path === "/slate/identity-reconcile");
  assert.ok(reconcileIndex >= 0);
  assert.deepEqual(writes[reconcileIndex].body, { season: 2000, week: 1, slate: "SUNDAY_MAIN" });
  const automaticBuildIndex = writes.findIndex((r, i) => i > reconcileIndex && r.path === "/slate/preparation/jobs" && r.body.action === "rebuild");
  assert.ok(automaticBuildIndex > reconcileIndex, "Identity reconciliation must precede the automatic prepared source snapshot");
  await page.getByText(/Unresolved salary identities: Synthetic unmatched player/).waitFor();
  assert.equal(await page.locator(".operations-optimizer-panel .inline-error").isVisible(), true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: artifacts + "/basics-desktop.png" });
  await panel.screenshot({ path: artifacts + "/options-desktop.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: artifacts + "/basics-mobile.png", fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Mobile page must not overflow horizontally");
  await panel.screenshot({ path: artifacts + "/options-mobile.png" });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Expanded options must fit mobile width");
  assert.deepEqual(errors, []);
  console.log("PASS: basic CSV actions, busy state, loaded evidence, visible optimizer options with collapsed preparation, real UI/API/queue/worker automatic preparation, consumption, reopen, preserved controls and pinned optimizer request. Synthetic source/model adapters; no live source or solver.");
} finally {
  await browser?.close(); worker.kill("SIGTERM"); await new Promise(r => appServer.close(r));
}
