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
const evidenceDir = process.env.OVERLAP_BROWSER_EVIDENCE || root + "artifacts/classic_construction_application";
mkdirSync(evidenceDir, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: "block" });
const page = await context.newPage();
const errors = [];
page.on("pageerror", e => errors.push(e.message));
const captured = [];
const reports = new Map();
const rawReports = new Map();
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
    rawReports.set(payload.optimizer_run_id, run.stdout);
    const fixture = JSON.parse(run.stdout)[0];
    reports.set(payload.optimizer_run_id, fixture);
    jobs.set(payload.optimizer_run_id, { optimizer_run_id: payload.optimizer_run_id });
    return reply({ job: { job_id: payload.optimizer_run_id } }, 202);
  }
  if (path.startsWith("/jobs/")) return reply({ status: "completed", result: jobs.get(path.split("/").at(-1)) });
  if (path.endsWith("/construction-review")) {
    const report = reports.get(path.split("/").at(-2))?.report;
    const run = spawnSync(root + ".venv/bin/python", ["backend/app/tests/product/construction_review_fixture.py"], {
      cwd: root, env: { ...process.env, PYTHONPATH: root }, input: JSON.stringify({ raw_fixture_json: rawReports.get(path.split("/").at(-2)), entry: Number(new URL(req.url()).searchParams.get("entry")), enforce_single_te: new URL(req.url()).searchParams.get("enforce_single_te") === "true" }),
      encoding: "utf8", timeout: 120000, maxBuffer: 32 * 1024 * 1024,
    });
    assert.equal(run.status, 0, run.stderr);
    return reply(JSON.parse(run.stdout));
  }
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
  const panel = page.locator(".classic-large-portfolio-controls");
  const te = page.getByRole("checkbox", { name: /Enforce single TE/ });
  assert.equal(await te.count(), 1);
  assert.equal(await te.isChecked(), true, "Existing default remains on");
  await panel.getByLabel("Number of lineups", { exact: true }).fill("5");
  await panel.getByLabel("Max player exposure (%)", { exact: true }).fill("80");
  await panel.getByLabel(/^Max lineups per primary game/).selectOption("3");
  await panel.getByLabel(/^Max shared players between lineups/).selectOption("5");
  // Team/game constraints retain their existing independent controls.
  await page.getByLabel(/^Max players \/ team/).fill("3");
  await page.getByLabel(/^Max players \/ game/).fill("5");
  for (const single of [true, false]) {
    await te.setChecked(single);
    await page.reload();
    await page.getByRole("button", { name: "Operations", exact: true }).click();
    assert.equal(await te.isChecked(), single, "Preference survives reload");
    // Existing team/game fields are session controls; restore same test frame.
    await page.getByLabel(/^Max players \/ team/).fill("3");
    await page.getByLabel(/^Max players \/ game/).fill("5");
    const network = page.waitForRequest(r => new URL(r.url()).pathname === "/api/optimizer/jobs");
    await page.getByRole("button", { name: "Run Optimizer", exact: true }).click();
    const payload = (await network).postDataJSON();
    assert.equal(payload.params.enforce_single_te, single);
    for (const [key, value] of Object.entries({ num_lineups: 5, max_exposure: .8, max_lineups_per_primary_game: 3, max_lineup_overlap: 5, max_players_per_team: 3, max_players_per_game: 5 })) assert.equal(payload.params[key], value, key);
    await page.waitForFunction(() => document.querySelector(".classic-large-portfolio-controls fieldset")?.disabled === false, null, { timeout: 120000 });
    await page.getByRole("heading", { name: "Classic construction summary", exact: true }).waitFor();
    const fixture = reports.get(payload.optimizer_run_id);
    assert.equal(fixture.saved_options.enforce_single_te, single);
    assert.equal(fixture.report.effective_strategy_contract.effective.pipeline_options.enforce_single_te, single);
    assert.equal(fixture.report.enforce_single_te, single);
    assert.equal(fixture.report.construction_summary.selected_count, 5);
    assert.equal(writes.filter(w => w.path.endsWith("construction-review")).length, single ? 0 : 2, "Report opening never reviews");
    await page.getByRole("button", { name: "Review construction tradeoffs", exact: true }).click();
    await page.getByText(/Each row restricts only the stated construction/).first().waitFor({ timeout: 120000 });
    const review = page.locator(".status-card").filter({ has: page.getByRole("heading", { name: "Classic construction summary", exact: true }) }).last();
    assert.ok((await review.innerText()).includes(single ? "excluded by user preference" : "TE FLEX / two TEs"));
    assert.ok((await review.innerText()).includes("NOT a lineup percentile"));
    await review.screenshot({ path: evidenceDir + `/review-single-te-${single}.png` });
    if (single) {
      // User changes only the existing checkbox and explicitly reviews the SAME
      // saved contract, without an optimizer submission or new portfolio.
      const optimizerCount = captured.length;
      await te.uncheck();
      await page.getByRole("button", { name: "Review construction tradeoffs", exact: true }).click();
      await page.getByText("Explicit changed construction setting: Enforce single TE only.", { exact: false }).first().waitFor({ timeout: 120000 });
      assert.equal(captured.length, optimizerCount);
      const teRow = review.getByRole("row").filter({ hasText: "TE FLEX / two TEs" });
      assert.ok((await teRow.innerText()).includes("Feasible"));
      await review.screenshot({ path: evidenceDir + "/same-pinned-frame-te-override.png" });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await review.screenshot({ path: evidenceDir + `/review-mobile-single-te-${single}.png` });
    await page.setViewportSize({ width: 1440, height: 1100 });
  }
  assert.equal(errors.length, 0, errors.join("\n"));
  writeFileSync(evidenceDir + "/browser-evidence.json", JSON.stringify({ captured, writes, errors, generatedUserPortfolio: false }, null, 2));
  console.log(JSON.stringify({ variants: captured.map(p => p.params.enforce_single_te), userPortfolioGenerated: false, reviewRequests: writes.filter(w => w.path.endsWith("construction-review")).length, errors }));
} catch (error) {
  writeFileSync(evidenceDir + "/failure.txt", await page.locator("body").innerText());
  await page.screenshot({ path: evidenceDir + "/failure.png", fullPage: true }); throw error;
} finally { await browser.close(); if (server) await new Promise(resolve => server.close(resolve)); }
