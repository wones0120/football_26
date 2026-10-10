// Isolated built UI; only frozen saved reports, all writes/network blocked.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const saved = JSON.parse(readFileSync(root + "artifacts/showdown_scenario_selection/reference/monday-week4.json"));
const report = JSON.parse(readFileSync(root + "artifacts/showdown_scenario_selection/monday-week4-C-accounting.json"));
const fixture = structuredClone(saved);
fixture.results[0][0].captain_family_coverage_report = report;
const server = createServer((req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  const file = resolve(root, "ui/dist", "." + (path === "/" ? "/index.html" : path));
  if (!file.startsWith(resolve(root, "ui/dist") + "/")) return res.writeHead(403).end();
  try { res.setHeader("content-type", file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html"); res.end(readFileSync(file)); }
  catch { res.writeHead(404).end(); }
});
await new Promise(r => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ headless: true, channel: "chrome" });
  for (const width of [1440, 390]) {
    const context = await browser.newContext({ viewport: { width, height: 1000 }, serviceWorkers: "block" });
    const page = await context.newPage(); const errors = [], writes = [];
    page.on("pageerror", error => errors.push(error.message));
    await context.route("**/*", route => new URL(route.request().url()).origin === base && route.request().method() === "GET" ? route.continue() : route.abort());
    await context.route("**/api/**", route => {
      const request = route.request(), url = new URL(request.url()), path = url.pathname.replace(/^\/api/, "");
      const reply = json => route.fulfill({ contentType: "application/json", body: JSON.stringify(json) });
      if (request.method() !== "GET") { writes.push(path); return route.abort(); }
      if (path === "/meta/current") return reply({ season: 2026, week: 4, slate: "MONDAY_NIGHT" });
      if (path === "/optimizer/runs") return reply({ runs: url.searchParams.get("contest_format") === "showdown" ? [{
        optimizer_run_id: saved.job_id, season: 2026, week: 4, slate: "MONDAY_NIGHT", contest_format: "showdown", objective: "gpp",
        strategy: saved.strategy, status: "completed", saved_report_available: true, lineup_count: 5,
        created_at: saved.created_at, updated_at: saved.updated_at }] : [] });
      if (path.startsWith("/optimizer/results/")) return reply(fixture);
      if (path === "/optimizer/projections") return reply({ runs: [] });
      if (path === "/jobs" || path === "/weekly/runs") return reply({ rows: [] });
      return route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"Unavailable in isolated fixture"}' });
    });
    await page.addInitScript(() => localStorage.setItem("football-26-active-slate-context", JSON.stringify({ season: 2026, week: 4, slate: "MONDAY_NIGHT" })));
    await page.goto(base);
    await page.getByRole("button", { name: width === 390 ? "Ops" : "Operations", exact: true }).click();
    await page.locator(".operations-optimizer-panel").getByRole("combobox", { name: "Format", exact: true }).selectOption("showdown");
    await page.locator(".optimizer-history-table").getByRole("button", { name: "Open results", exact: true }).click();
    const heading = page.getByRole("heading", { name: "Scenario portfolio accounting", exact: true });
    try { await heading.waitFor({ timeout: 10000 }); }
    catch (error) {
      await page.screenshot({ path: root + `artifacts/showdown_scenario_selection/fixture-failure-${width}.png` });
      console.log((await page.locator("body").innerText()).slice(-18000), errors);
      throw error;
    }
    const section = heading.locator("..");
    assert.equal(await section.locator("tbody tr").count(), 3);
    assert.match(await section.innerText(), /physical entries: no/);
    assert.match(await section.innerText(), /Identical physical roster/);
    await heading.scrollIntoViewIfNeeded();
    const box = await section.locator(".scroll-table").boundingBox();
    assert.ok(box && box.width <= width, "Accounting table must stay inside its scroll container");
    assert.ok(await section.locator(".scroll-table").evaluate(element => element.scrollHeight <= element.clientHeight + 1),
      "All three accounting rows must be visible without a second vertical scrollbar");
    await section.screenshot({ path: root + `artifacts/showdown_scenario_selection/accounting-${width}.png` });
    await page.locator(".operations-optimizer-panel details").filter({ has: page.getByText("Optimizer options", { exact: true }) }).locator("summary").click();
    const option = page.getByRole("checkbox", { name: "Soft scenario diversity (experimental)", exact: true });
    await option.waitFor();
    assert.equal(await option.isChecked(), false);
    await option.check();
    assert.equal(await option.isChecked(), true);
    assert.deepEqual(writes, []);
    assert.deepEqual(errors, []);
    await context.close();
    console.log(`Scenario accounting ${width}: passed; no API writes`);
  }
} finally {
  await browser?.close();
  await new Promise(r => server.close(r));
}
