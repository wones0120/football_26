// Real built App, read-only synthetic saved runs. No live API, sources or solver.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const artifacts = root + "artifacts/optimizer_navigation";
mkdirSync(artifacts, { recursive: true });
const server = createServer((req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  const file = resolve(root, "ui/dist", "." + (path === "/" ? "/index.html" : path));
  if (!file.startsWith(resolve(root, "ui/dist") + "/")) return res.writeHead(403).end();
  try {
    res.setHeader("content-type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html");
    res.end(readFileSync(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true, channel: "chrome" });
  for (const [width, selectedFormat] of [[1440, "classic"], [1440, "showdown"], [390, "classic"], [390, "showdown"]]) {
    const height = width === 390 ? 844 : 1100;
    const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: "block" });
    const page = await context.newPage(); const errors = []; const writes = [];
    const history = format => ({ optimizer_run_id: `fixture-${format}`, season: 2000, week: 1, slate: "SUNDAY_MAIN",
      contest_format: format, objective: "gpp", strategy: format === "classic" ? "classic_large_gpp_v1" : "showdown_gpp_portfolio_v3",
      status: "completed", saved_report_available: true, lineup_count: 0, created_at: "2000-01-01T00:00:00Z",
      updated_at: "2000-01-01T00:00:00Z", started_at: null, completed_at: null });
    page.on("pageerror", error => errors.push(error.message));
    await context.route("**/*", route => new URL(route.request().url()).origin === base && route.request().method() === "GET" ? route.continue() : route.abort());
    await context.route("**/api/**", route => {
      const request = route.request(); const url = new URL(request.url()); const path = url.pathname.replace(/^\/api/, "");
      const reply = (json, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(json) });
      if (request.method() !== "GET") { writes.push(path); return route.abort(); }
      if (path === "/meta/current") return reply({ season: 2000, week: 1, slate: "SUNDAY_MAIN" });
      if (path === "/optimizer/runs") return reply({ runs: [history(url.searchParams.get("contest_format") || "classic")] });
      if (path.startsWith("/optimizer/results/")) {
        const format = path.endsWith("showdown") ? "showdown" : "classic";
        return reply({ job_id: `fixture-${format}`, status: "completed", strategy: history(format).strategy,
          strategy_config: {}, contest_format: format, objective: "gpp", lineage_persisted: true, results: [],
          message: "Synthetic saved report; no optimizer executed" });
      }
      if (path === "/optimizer/projections") return reply({ runs: [] });
      if (path === "/jobs" || path === "/weekly/runs") return reply({ rows: [] });
      if (path === "/slate/preparation") return reply({ scope: { season: 2000, week: 1, slate: "SUNDAY_MAIN" },
        server_time: "2000-01-01T00:00:00Z", inputs: { salaries: [], injuries: [] }, jobs: [],
        prelock: true, latest_build: null, build_current: false, entry_ready: false, limitations: [] });
      return reply({ detail: "Unavailable in isolated navigation fixture" }, 503);
    });
    await page.addInitScript(({ selectedFormat }) => {
      localStorage.setItem("football-26-active-slate-context", JSON.stringify({ season: 2000, week: 1, slate: "SUNDAY_MAIN" }));
      localStorage.setItem("football-26-run-selections", JSON.stringify({ "2000:1:SUNDAY_MAIN": { optimizerRunId: `fixture-${selectedFormat}` } }));
      window.resultScrolls = [];
      const nativeScroll = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (...args) {
        if (this.classList.contains("optimizer-results")) window.resultScrolls.push(this.textContent);
        return nativeScroll.apply(this, args);
      };
    }, { selectedFormat });
    await page.goto(base);
    await page.getByRole("button", { name: width === 390 ? "Ops" : "Operations", exact: true }).click();
    const format = page.locator(".operations-optimizer-panel").getByRole("combobox", { name: "Strategy", exact: true });
    // Exercise a cold restoration and repeated mode changes after report polling.
    await format.selectOption(selectedFormat === "classic" ? "showdown" : "classic");
    await format.evaluate(element => element.scrollIntoView({ block: "center" }));
    await format.selectOption(selectedFormat);
    await page.locator(".optimizer-results").getByText(`Job ID: fixture-${selectedFormat}`, { exact: true }).waitFor();
    await page.waitForTimeout(800); // Allow the unwanted smooth scroll to finish if present.
    assert.equal(await page.evaluate(() => window.resultScrolls.length), 0, "Automatic restoration must not scroll to prior results");
    const bounds = await format.boundingBox();
    assert.ok(bounds && bounds.y > 0 && bounds.y < height, "Format selector must stay in view after restoration");
    for (const target of [selectedFormat === "classic" ? "showdown" : "classic", selectedFormat]) {
      await format.selectOption(target);
      await page.waitForTimeout(800);
      assert.equal(await page.evaluate(() => window.resultScrolls.length), 0, "Format switches must not navigate to results");
    }
    await page.screenshot({ path: artifacts + `/${selectedFormat}-${width}-format-preserved.png` });
    // Intentional history navigation still scrolls to the saved report.
    const row = page.locator(".optimizer-history-table tbody tr").filter({ hasText: `fixture-${selectedFormat}`.slice(0, 8) });
    await row.getByRole("button", { name: /^(Open|Reopen) results$/ }).click();
    await page.waitForFunction(() => window.resultScrolls.length === 1);
    await page.waitForTimeout(800);
    assert.ok(await page.locator(".optimizer-results").evaluate(element => element.getBoundingClientRect().top < innerHeight));
    assert.deepEqual(errors, []);
    assert.deepEqual(writes, [], "Navigation cannot import, rebuild or run an optimizer");
    await context.close();
  }
  console.log("PASS: Classic/Showdown automatic saved-run restoration preserves form position; explicit Open/Reopen results scrolls. No API writes or optimizer execution.");
} finally {
  await browser?.close(); await new Promise(r => server.close(r));
}
