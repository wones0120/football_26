// Runs the actual App entry point. All API traffic is intercepted: no live writes.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
// Serve the unchanged Vite output and real index/main/App route, not a test harness.
let server;
let base = process.env.OVERLAP_APP_URL;
if (!base) {
  const dist = resolve(root, "ui/dist");
  assert.ok(!readFileSync(dist + "/index.html", "utf8").includes("/@vite/client"), "Production build required");
  server = createServer((req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    const file = resolve(dist, "." + (path === "/" ? "/index.html" : path));
    if (!file.startsWith(dist + "/")) { res.writeHead(403).end(); return; }
    try {
      const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : file.endsWith(".svg") ? "image/svg+xml" : "text/html";
      res.writeHead(200, { "Content-Type": type }); res.end(readFileSync(file));
    } catch { res.writeHead(404).end(); }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${server.address().port}`;
}
assert.match(base, /^http:\/\/(localhost|127\.0\.0\.1):\d+\/?$/);
const evidenceDir = process.env.OVERLAP_BROWSER_EVIDENCE || root + "artifacts/classic_large_gpp_live_overlap";
mkdirSync(evidenceDir, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: "block" });
const page = await context.newPage();
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const captured = [];
const reports = new Map();
const jobs = new Map();
const writes = [];
let corruptReturnedContract = false;
let pausePreparation = false;
let releasePreparation;
const assets = [];
page.on("response", async response => {
  if (response.url().startsWith(base) && new URL(response.url()).pathname.endsWith(".js")) {
    const bytes = await response.body();
    assets.push({ url: response.url(), sha256: createHash("sha256").update(bytes).digest("hex") });
  }
});
const readiness = { status: "pass", score: 100, summary: { pass: 1, warn: 0, fail: 0 }, checks: [],
  gates: Object.fromEntries(["prediction", "classic_gpp", "classic_cash", "showdown_gpp", "showdown_cash"].map(k => [k, { status: "pass", score: 100, summary: { pass: 1, warn: 0, fail: 0 }, blocking_checks: [], attention_checks: [], message: "Synthetic ready" }])) };
await context.route("**/*", route => {
  const request = route.request();
  // Fail closed even if a future build changes its API base away from /api.
  if (request.method() !== "GET" || new URL(request.url()).origin !== new URL(base).origin) return route.abort();
  return route.continue();
});
await context.route("**/api/**", async route => {
  const req = route.request();
  const path = new URL(req.url()).pathname.replace(/^\/api/, "");
  const reply = (json, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
  if (req.method() !== "GET") writes.push({ path, body: req.postDataJSON() });
  if (path === "/meta/current") return reply({ season: 2000, week: 1, slate: "SUNDAY_MAIN" });
  if (path === "/slate/readiness") return reply(readiness);
  if (path === "/slate/identity-reconcile") {
    if (pausePreparation) await new Promise(resolve => { releasePreparation = resolve; });
    return reply({ salary_rows_seen: 72, salary_rows_resolved: 72, salary_rows_quarantined: 0 });
  }
  if (path === "/features/matrix/build") return reply({ rows_written: 72, message: "Synthetic features" });
  if (path === "/slate/starting-qbs") return reply({ rows_written: 8, message: "Synthetic starters", candidates: [], starters: [] });
  if (path === "/predict/run") {
    jobs.set("fixture-projection-job", { projection_run_id: "synthetic-projection", rows_written: 72, target_persisted: true, message: "Synthetic projections" });
    return reply({ job: { job_id: "fixture-projection-job" } }, 202);
  }
  if (path === "/ownership/run") return reply({ rows_written: 72, ownership_run_id: "synthetic-ownership", message: "Synthetic ownership" });
  if (path === "/optimizer/projections") return reply({ runs: [] });
  if (path === "/optimizer/jobs") {
    const payload = req.postDataJSON();
    // Preserve the browser's exact JSON. Never call a replacement request builder.
    assert.equal(payload.season, 2000);
    assert.equal(payload.week, 1);
    captured.push(payload);
    if (process.env.OVERLAP_CAPTURE_ONLY) return reply({ detail: "Captured; no optimizer executed" }, 422);
    if (corruptReturnedContract) {
      const fixture = structuredClone([...reports.values()][0]);
      fixture.report.job_id = payload.optimizer_run_id;
      fixture.report.effective_strategy_contract.requested.max_lineup_overlap = null;
      reports.set(payload.optimizer_run_id, fixture);
      jobs.set(payload.optimizer_run_id, { optimizer_run_id: payload.optimizer_run_id });
      return reply({ job: { job_id: payload.optimizer_run_id } }, 202);
    }
    const run = spawnSync(root + ".venv/bin/python", ["backend/app/tests/product/overlap_ui_fixture.py"], {
      cwd: root, env: { ...process.env, PYTHONPATH: root }, input: JSON.stringify([payload]), encoding: "utf8", timeout: 120000, maxBuffer: 32 * 1024 * 1024,
    });
    assert.equal(run.status, 0, run.stderr);
    const fixture = JSON.parse(run.stdout)[0];
    reports.set(payload.optimizer_run_id, fixture);
    jobs.set(payload.optimizer_run_id, { optimizer_run_id: payload.optimizer_run_id });
    return reply({ job: { job_id: payload.optimizer_run_id } }, 202);
  }
  if (path.startsWith("/jobs/")) return reply({ status: "completed", result: jobs.get(path.split("/").at(-1)) });
  if (path.startsWith("/optimizer/results/")) return reply(reports.get(path.split("/").at(-1))?.report ?? {}, 200);
  if (path === "/optimizer/runs") return reply({ runs: [] });
  if (path === "/jobs" || path === "/weekly/runs") return reply({ rows: [] });
  // Unknown requests fail closed, including readiness requests that record data.
  return reply({ detail: "Unavailable in deterministic browser fixture" }, 503);
});
await page.addInitScript(() => {
  localStorage.setItem("football-26-active-slate-context", JSON.stringify({ season: 2000, week: 1, slate: "SUNDAY_MAIN" }));
});
try {
  await page.goto(base);
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  await page.getByLabel(/^Contest Strategy/).selectOption("classic_large_gpp_v1");
  const panel = page.locator(".classic-large-portfolio-controls");
  const overlap = panel.getByLabel(/^Max shared players between lineups/);
  await panel.getByLabel("Number of lineups", { exact: true }).fill("5");
  await panel.getByLabel("Max player exposure (%)", { exact: true }).fill("80");
  await panel.getByLabel(/^Max lineups per primary game/).selectOption("3");
  await overlap.selectOption("5");
  assert.equal(await overlap.inputValue(), "5");
  // Unrelated controls and mode changes must preserve the explicit Large choice.
  await panel.getByLabel(/^Max lineups per primary game/).selectOption("2");
  assert.equal(await overlap.inputValue(), "5");
  await panel.getByLabel(/^Max lineups per primary game/).selectOption("3");
  await panel.getByLabel("Number of lineups", { exact: true }).fill("6");
  assert.equal(await overlap.inputValue(), "5");
  await panel.getByLabel("Number of lineups", { exact: true }).fill("5");
  await panel.getByLabel("Max player exposure (%)", { exact: true }).fill("60");
  assert.equal(await overlap.inputValue(), "5");
  await panel.getByLabel("Max player exposure (%)", { exact: true }).fill("80");
  await page.getByLabel(/^Contest Strategy/).selectOption("classic_small_field_gpp");
  await page.getByLabel(/^Contest Strategy/).selectOption("classic_large_gpp_v1");
  assert.equal(await overlap.inputValue(), "5");
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Format/ }).selectOption("showdown");
  await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: /Format/ }).selectOption("classic");
  assert.equal(await overlap.inputValue(), "5");
  await page.reload();
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  assert.equal(await overlap.inputValue(), "5");
  assert.equal(await panel.getByLabel("Number of lineups", { exact: true }).inputValue(), "5");
  assert.equal(await panel.getByLabel("Max player exposure (%)", { exact: true }).inputValue(), "80");
  assert.equal(await panel.getByLabel(/^Max lineups per primary game/).inputValue(), "3");
  await page.screenshot({ path: evidenceDir + "/form-before-submit.png", fullPage: true });
  await panel.screenshot({ path: evidenceDir + "/portfolio-controls-desktop.png" });
  const summaryPanel = page.getByLabel("Portfolio settings to submit", { exact: true });
  assert.equal(await summaryPanel.locator("li").count(), 6);
  assert.equal(await page.getByRole("button", { name: "Run Optimizer", exact: true }).evaluate(button => button.previousElementSibling?.getAttribute("aria-label")), "Portfolio settings to submit");
  await summaryPanel.screenshot({ path: evidenceDir + "/request-summary-desktop.png" });
  const matrix = [];
  for (const value of process.env.OVERLAP_CAPTURE_ONLY ? [5] : [5, 4, 6, 7, null]) {
    await overlap.selectOption(value === null ? "default" : String(value));
    assert.equal(await overlap.inputValue(), value === null ? "default" : String(value));
    const persisted = await page.evaluate(() => JSON.parse(localStorage.getItem("football-26-classic-large-gpp-controls")));
    assert.equal(persisted.maxLineupOverlap, value);
    const summary = await summaryPanel.innerText();
    assert.ok(summary.includes(`Max shared players between lineups: ${value ?? "Strategy default (7)"}`));
    assert.ok(summary.includes("Lineups: 5") && summary.includes("Max player exposure: 80%") && summary.includes("Max lineups per primary game: 3"));
    assert.ok(summary.includes("Elevated-risk player exposure: Strategy default") && summary.includes("Max elevated-risk players per lineup: Strategy default"));
    const network = page.waitForRequest(r => new URL(r.url()).pathname === "/api/optimizer/jobs");
    pausePreparation = true;
    const preparation = page.waitForRequest(r => new URL(r.url()).pathname === "/api/slate/identity-reconcile");
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    await preparation;
    assert.equal(await overlap.isDisabled(), true);
    if (!process.env.OVERLAP_CAPTURE_ONLY) assert.equal(await page.getByRole("checkbox", { name: /Create one standalone long-shot lineup/ }).isDisabled(), true);
    assert.equal(await overlap.inputValue(), value === null ? "default" : String(value));
    pausePreparation = false;
    releasePreparation();
    const payload = (await network).postDataJSON();
    assert.equal(payload.params.num_lineups, 5);
    assert.equal(payload.params.max_exposure, .8);
    assert.equal(payload.params.max_lineups_per_primary_game, 3);
    assert.equal(payload.params.max_lineup_overlap, value);
    const trace = payload.params.portfolio_submission_trace;
    for (const key of ["rendered_dropdown_value", "local_component_state_value", "parent_form_state_value", "summary_value", "submit_handler_value", "request_builder_input_value", "serialized_request_object_value"]) assert.equal(trace[key], value, key);
    await page.waitForFunction(() => document.querySelector(".classic-large-portfolio-controls fieldset")?.disabled === false, null, { timeout: 120000 });
    const fixture = reports.get(payload.optimizer_run_id);
    if (fixture) {
      for (const layer of [fixture.api_request.params, fixture.backend_parsed_request.params, fixture.saved_options]) assert.equal(layer.max_lineup_overlap, value);
      const contract = fixture.report.effective_strategy_contract;
      assert.equal(contract.requested.max_lineup_overlap, value);
      assert.equal(contract.effective.max_lineup_overlap, value ?? 7);
      assert.equal(contract.sources.max_lineup_overlap, value === null ? "strategy_default" : "request");
      assert.equal(fixture.api_request.params.portfolio_submission_trace.backend_parsed_request_value, value);
      assert.equal(fixture.report.portfolio_submission_trace.saved_contract_requested_value, value);
      assert.equal(fixture.report.status, "completed");
      const row = fixture.report.portfolio_controls_report.settings.find(r => r.key === "max_lineup_overlap");
      assert.ok(row.achieved <= (value ?? 7));
      const sets = fixture.report.results.map(lineup => new Set(lineup.map(p => p.player_id)));
      for (let i = 0; i < sets.length; i++) for (let j = 0; j < i; j++) assert.ok([...sets[i]].filter(id => sets[j].has(id)).length <= (value ?? 7));
      assert.equal(fixture.report.portfolio_controls_report.validation.status, "verified");
      matrix.push({ visible: value, persisted, summary, network: payload, backend_parsed: fixture.backend_parsed_request.params, saved_requested: contract.requested.max_lineup_overlap, effective: contract.effective.max_lineup_overlap, source: contract.sources.max_lineup_overlap, achieved: row.achieved });
    } else matrix.push({ visible: value, persisted, summary, network: payload });
  }
  assert.equal(errors.length, 0, errors.join("\n"));
  await page.screenshot({ path: evidenceDir + "/saved-report.png", fullPage: true });
  let rejectionVisible = false;
  let preSubmitRejectionVisible = false;
  let dropdownMismatchBlocked = false;
  if (!process.env.OVERLAP_CAPTURE_ONLY) {
    // Simulate native DOM restoration without a React change event. This is a
    // regression scenario, not an assertion about the historical user's tab.
    await overlap.selectOption("default");
    await overlap.evaluate(select => { select.value = "5"; });
    assert.equal(await overlap.inputValue(), "5");
    const writesBefore = writes.length;
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    await page.getByText(/Portfolio dropdown\/state mismatch: dropdown shows 5, controlled React value null/).waitFor();
    assert.equal(writes.length, writesBefore, "DOM mismatch must block even upstream preparation writes");
    const mismatchTrace = await page.evaluate(() => JSON.parse(localStorage.getItem("football-26-last-portfolio-submission-trace")));
    assert.equal(mismatchTrace.rendered_dropdown_value, 5);
    assert.equal(mismatchTrace.parent_form_state_value, null);
    writeFileSync(evidenceDir + "/dropdown-state-mismatch.json", JSON.stringify(mismatchTrace, null, 2));
    dropdownMismatchBlocked = true;
    await overlap.selectOption("5");
    const exposureInput = panel.locator('input[data-portfolio-field="max_exposure"]');
    await exposureInput.evaluate(input => { input.value = "60"; });
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    await page.getByText(/Portfolio control\/summary mismatch: max_exposure shows 0.6, summary\/request contains 0.8/).waitFor();
    assert.equal(writes.length, writesBefore, "Other explicit control mismatches must also block preparation");
    await exposureInput.fill("80");
    await page.setViewportSize({ width: 390, height: 844 });
    await panel.screenshot({ path: evidenceDir + "/portfolio-controls-mobile.png" });
    await summaryPanel.screenshot({ path: evidenceDir + "/request-summary-mobile.png" });
    await page.setViewportSize({ width: 1440, height: 1100 });
    const requestCountBefore = captured.length;
    // Fault injection at serialization only. The real form/handler/builder still run.
    await page.evaluate(() => {
      window.overlapOriginalStringify = JSON.stringify;
      JSON.stringify = function(value, replacer, space) {
        if (value?.strategy === "classic_large_gpp_v1" && value?.optimizer_run_id && value?.params) {
          value = { ...value, params: { ...value.params, max_lineup_overlap: undefined } };
        }
        return window.overlapOriginalStringify(value, replacer, space);
      };
    });
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    await page.getByText(/Portfolio settings to submit mismatch: max_lineup_overlap displays 5/).waitFor();
    assert.equal(captured.length, requestCountBefore, "Mismatch must fail before any optimizer network submission");
    preSubmitRejectionVisible = true;
    await page.evaluate(() => { JSON.stringify = window.overlapOriginalStringify; delete window.overlapOriginalStringify; });
    corruptReturnedContract = true;
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    await page.getByText(/Optimizer overlap consistency failure: submitted 5;/).waitFor();
    rejectionVisible = true;
  }
  assert.equal(errors.length, 0, errors.join("\n"));
  if (!process.env.OVERLAP_APP_URL) for (const asset of assets) {
    assert.equal(asset.sha256, createHash("sha256").update(readFileSync(root + "ui/dist" + new URL(asset.url).pathname)).digest("hex"), "Served asset must equal the built file");
  }
  const build = { base, productionBuild: !process.env.OVERLAP_APP_URL, assets, sourceCommit: spawnSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).stdout.trim(), workingTree: "uncommitted changes included", generatedUserPortfolio: false };
  writeFileSync(evidenceDir + "/browser-requests.json", JSON.stringify({ build, matrix, writes, errors, rejectionVisible, preSubmitRejectionVisible, dropdownMismatchBlocked }, null, 2));
  console.log(JSON.stringify({ build, matrix: matrix.map(r => ({ visible: r.visible, network: r.network.params.max_lineup_overlap, savedRequested: r.saved_requested, effective: r.effective, source: r.source, achieved: r.achieved })), rejectionVisible, preSubmitRejectionVisible, dropdownMismatchBlocked, errors }));
} catch (error) { writeFileSync(evidenceDir + "/failure.txt", await page.locator("body").innerText() + "\n" + errors.join("\n")); await page.screenshot({ path: evidenceDir + "/failure.png", fullPage: true }); throw error; } finally { await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
