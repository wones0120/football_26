// Isolated browser contract: source work is queued only by Prepare, never Run.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = resolve(import.meta.dirname, "../..");
const server = createServer((req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  const file = resolve(root, "ui/dist", "." + (path === "/" ? "/index.html" : path));
  if (!file.startsWith(resolve(root, "ui/dist") + "/")) return res.writeHead(403).end();
  try { res.setHeader("content-type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html"); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, channel: "chrome" });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = []; page.on("pageerror", e => errors.push(e.message));
  let ready = false; let lostOptimizerReceipt = false; const writes = [];
  let releaseInitialCheck;
  const initialCheck = new Promise(resolve => { releaseInitialCheck = resolve; });
  const scope = { season: 2026, week: 5, slate: "SUNDAY_MAIN" };
  const build = { ...scope, action: "prepare", contest_format: "classic", prepared_input_job_id: "prepared-id",
    audit_url: "/api/jobs/prepared-id",
    projection_run_id: "verified-projection", feature_run_id: "verified-features", source_sha256: "sha",
    data_readiness: { status: "READY" }, availability_overrides: [], assume_questionable_out: false, limitations: [], consumption: {} };
  await page.route("**/api/**", async route => {
    const req = route.request(); const path = new URL(req.url()).pathname.replace(/^\/api/, "");
    const reply = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (req.method() !== "GET") writes.push({ path, body: req.postDataJSON() });
    if (path === "/models/pipeline/status") {
      const summary = operation => ({ operation, status: "completed", status_at: new Date().toISOString(),
        latest_attempt: { status: "completed", rows_written: 582, progress_percent: 100,
          result: { calibration_metrics: { input_coverage: { unresolved_salary_source_keys: ["a", "b", "c", "d", "e"] } } } } });
      return reply({ ...scope, has_active_jobs: false, features: summary("features"),
        projections: summary("projections"), symbolic: { operation: "symbolic", status: "not_run" } });
    }
    if (path === "/ingest/salaries") return reply({ rows_raw: 587, rows_curated: 587, rows_unresolved: 7 });
    if (path === "/slate/preparation") { await initialCheck; return reply({ scope, server_time: new Date().toISOString(), inputs: {}, jobs: [],
      prelock: true, build_current: ready, latest_build: ready ? build : null, entry_ready: false, limitations: [] }); }
    if (path === "/slate/preparation/jobs") return reply({ created: true, job: { job_id: "prepared-id", status: "queued" } }, 202);
    if (path === "/jobs/prepared-id") { ready = true; return reply({ job_id: "prepared-id", status: "completed", result: build }); }
    if (path === "/optimizer/jobs") {
      if (!lostOptimizerReceipt) { lostOptimizerReceipt = true; return route.abort("timedout"); }
      return reply({ detail: "Fixture verified request; no solver invoked" }, 409);
    }
    if (path === "/optimizer/projections" || path === "/optimizer/runs") return reply({ runs: [] });
    if (path === "/weekly/runs") return reply({ rows: [] });
    return reply({ detail: "Unavailable in isolated fixture" }, 503);
  });
  await page.addInitScript(scope => localStorage.setItem("football-26-active-slate-context", JSON.stringify(scope)), scope);
  await page.goto(base);
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  const run = page.getByRole("button", { name: "Run Optimizer", exact: true });
  assert.equal(await run.isDisabled(), true);
  await page.locator("#optimizer-readiness-status").getByText(/Checking saved slate readiness/).waitFor();
  assert.equal(await page.getByRole("progressbar", { name: "Optimizer readiness in progress" }).count(), 1);
  const loadingDir = resolve(root, "artifacts/optimizer_readiness_status"); mkdirSync(loadingDir, { recursive: true });
  await page.locator(".operations-optimizer-panel").screenshot({ path: resolve(loadingDir, "loading-desktop.png") });
  releaseInitialCheck();
  await page.getByText("Preparation required before optimization", { exact: true }).waitFor();
  await page.getByLabel("Salary file", { exact: true }).fill("/tmp/fixture-salaries.csv");
  await page.getByRole("button", { name: "Load salary CSV", exact: true }).click();
  await page.getByText(/7 unresolved salary identities/).waitFor();
  assert.equal(await run.isDisabled(), true);
  assert.equal(await page.locator('[aria-labelledby="prepare-slate-title"]').evaluate(el =>
    Boolean(el.compareDocumentPosition(document.querySelector('.operations-model-panel')) & Node.DOCUMENT_POSITION_FOLLOWING)), true);
  await page.getByRole("button", { name: "Prepare slate for optimization", exact: true }).click();
  await page.getByText("Prepared — ready to optimize", { exact: true }).waitFor();
  assert.equal(await run.isEnabled(), true);
  await page.locator("#optimizer-readiness-status").getByText("Ready to optimize — prepared inputs verified.").waitFor();
  assert.equal(await page.getByRole("progressbar", { name: "Optimizer readiness in progress" }).count(), 0);
  await run.click();
  await page.getByRole("alert").filter({ hasText: "Fixture verified request" }).waitFor();
  assert.deepEqual(writes.map(r => r.path), ["/ingest/salaries", "/slate/preparation/jobs", "/optimizer/jobs", "/optimizer/jobs"]);
  assert.deepEqual(writes[2].body, writes[3].body); // A lost receipt never creates a new run ID.
  assert.equal(writes[1].body.action, "prepare");
  assert.equal(writes[1].body.ownership_required, true);
  assert.equal(writes[2].body.objective, "gpp");
  assert.equal(writes[2].body.strategy, "classic_large_gpp_v1");
  assert.equal(writes[2].body.params.num_lineups, 5);
  assert.equal(await page.getByText(/best cash-oriented lineup first/).count(), 0);
  assert.equal(writes[2].body.params.prepared_input_job_id, "prepared-id");
  assert.equal(writes[2].body.projection_run_id, "verified-projection");
  const dir = resolve(root, "artifacts/optimizer_timeout_recovery"); mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: resolve(dir, "desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: resolve(dir, "mobile.png"), fullPage: true });
  const overflow = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
    elements: [...document.querySelectorAll("body *")].filter(el => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 12).map(el => ({ tag: el.tagName, cls: el.className, right: el.getBoundingClientRect().right })) }));
  assert.equal(overflow.scroll <= overflow.width + 1, true, JSON.stringify(overflow));
  await page.getByTestId("preparation-tools").locator(":scope > summary").click();
  await page.getByText('Prepared build and consumption summary', { exact: true }).click();
  assert.equal(await page.getByRole('link', { name: 'Open full saved preparation audit' }).getAttribute('href'), '/api/jobs/prepared-id');
  await page.getByRole("button", { name: "Open Model", exact: true }).click();
  await page.getByText("5 unresolved salary records were excluded.", { exact: false }).waitFor();
  assert.equal(await page.locator(".pipeline-result-card.status-warning").count() > 0, true);
  assert.deepEqual(errors, []);
  console.log("PASS: prepare/optimize separation, disabled state, exact run IDs, desktop/mobile");
} finally { await browser.close(); await new Promise(r => server.close(r)); }
