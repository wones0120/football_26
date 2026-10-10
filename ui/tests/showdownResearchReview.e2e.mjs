// Actual App/Vite build with frozen API fixtures; every network write is blocked.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../", import.meta.url));
const dist = resolve(root, "ui/dist");
const evidence = resolve(root, "artifacts/showdown_research_review");
const notes = JSON.parse(readFileSync(resolve(root, "docs/product/showdown_research_notes.json"), "utf8"));
// Two-entry display subset of the original four-entry Week 4 control.
const packet = JSON.parse(readFileSync(resolve(evidence, "ui_packet_fixture.json"), "utf8"));
let packetResponse = packet;
const server = createServer((req, res) => {
  const pathname = new URL(req.url, "http://localhost").pathname;
  const file = resolve(dist, "." + (pathname === "/" ? "/index.html" : pathname));
  if (!file.startsWith(dist + "/")) { res.writeHead(403).end(); return; }
  try {
    res.writeHead(200, { "Content-Type": file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html" });
    res.end(readFileSync(file));
  } catch { res.writeHead(404).end(); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const base = `http://127.0.0.1:${server.address().port}`;
mkdirSync(evidence, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: "chrome" });
const calls = [], errors = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, serviceWorkers: "block" });
  const page = await context.newPage();
  page.on("pageerror", e => errors.push(e.message));
  // No unmocked API or external requests; static assets from the build only.
  await context.route("**/*", route => {
    const req = route.request(), url = new URL(req.url());
    if (url.pathname.startsWith("/api/")) {
      calls.push({ path: url.pathname, method: req.method() });
      if (req.method() !== "GET") return route.abort();
      const path = url.pathname.replace(/^\/api/, "");
      const reply = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (path === "/learning/research/showdown") return reply(notes);
      if (path.endsWith("/ai-showdown-packet/download")) {
        assert.equal(url.searchParams.get("format"), "json");
        return reply(packetResponse);
      }
      if (path === "/optimizer/runs") return reply({ runs: url.searchParams.get("contest_format") === "showdown" ? [{
        optimizer_run_id: packet.run.optimizer_run_id, season: 2026, week: 4, slate: "THURSDAY_NIGHT",
        contest_format: "showdown", objective: "gpp", strategy: "showdown_gpp_portfolio_v3", status: "completed",
        created_at: packet.run.created_at, completed_at: packet.run.created_at,
        lineup_count: 2, saved_report_available: true, message: "Frozen historical display fixture",
      }] : [] });
      if (path === "/optimizer/projections") return reply({ runs: [] });
      if (path === "/meta/current") return reply({ season: 2026, week: 4, slate: "THURSDAY_NIGHT" });
      if (path === "/weekly/runs") return reply({ rows: [] });
      if (path === "/model/defaults") return reply({
        showdown_captain_model_path: "docs/showdown_captain_model_2024_2025.json", showdown_captain_prior_strength: .35,
        classic_value_driver_model_path: "docs/main_slate_value_driver_analysis_2024_2025.json", classic_value_driver_prior_strength: .45,
        matchup_outcome_model_path: "docs/matchup_outcome_intelligence_2024_2025.json", matchup_outcome_prior_strength: .15,
        matchup_prior_gate_model_path: "docs/matchup_prior_gate_20slates_5000.json",
      });
      return reply({ detail: "Unavailable in isolated display fixture" }, 503);
    }
    if (req.method() === "GET" && url.origin === base) return route.continue();
    return route.abort();
  });
  await page.addInitScript(() => localStorage.setItem("football-26-active-slate-context", JSON.stringify({ season: 2026, week: 4, slate: "THURSDAY_NIGHT" })));
  await page.goto(base);
  await page.getByRole("button", { name: "Research Lab", exact: true }).click();
  const study = page.getByRole("region", { name: "Showdown research notes", exact: true });
  await study.getByText("2026 Captain Contest Consistency", { exact: true }).waitFor();
  await study.getByText("WR/TE Captain paired with own QB", { exact: true }).click();
  await study.getByText("Early account performance did not persist collectively", { exact: true }).click();
  assert.match(await study.innerText(), /88\.9%.*81\.1%/);
  assert.match(await study.innerText(), /9\.7%.*10\.0%/);
  assert.equal(await study.getByText(notes.label, { exact: true }).count(), 6);
  assert.equal(await study.locator("button,input,select").count(), 1, "Research card has only the prospective research refresh action");
  await study.screenshot({ path: resolve(evidence, "research-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await study.scrollIntoViewIfNeeded();
  assert.ok(await study.evaluate(el => el.getBoundingClientRect().width <= 390));
  await study.screenshot({ path: resolve(evidence, "research-mobile.png") });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.getByRole("button", { name: "Operations", exact: true }).click();
  assert.deepEqual(errors, [], "App navigation must not raise render errors");
  await page.locator(".operations-optimizer-panel").getByLabel("Format").selectOption("showdown");
  await page.getByRole("button", { name: "Prelock review checklist", exact: true }).click();
  const checklist = page.getByLabel("Nonbinding prelock review checklist", { exact: true });
  await checklist.waitFor();
  assert.match(await checklist.innerText(), /Frozen cutoff/);
  assert.match(await checklist.innerText(), /3 of 6/);
  assert.match(await checklist.innerText(), /Projected ownership: unavailable/);
  assert.match(await checklist.innerText(), /WR\/TE CPT own QB/i);
  await checklist.getByText("QB families: generation versus quality filtering", { exact: true }).click();
  assert.match(await checklist.innerText(), /generation reason unavailable|quality filtering|represented/);
  assert.equal(await checklist.locator("button,input,select").count(), 0, "Checklist has no selection controls");
  await checklist.screenshot({ path: resolve(evidence, "checklist-desktop.png") });
  await page.setViewportSize({ width: 390, height: 844 });
  await checklist.scrollIntoViewIfNeeded();
  assert.ok(await checklist.evaluate(el => el.getBoundingClientRect().width <= 390));
  assert.ok(await checklist.locator(".saved-contest-scroll").first().evaluate(el => el.scrollWidth > el.clientWidth),
    "Coverage uses horizontal scrolling rather than unreadable compressed columns on mobile");
  await checklist.screenshot({ path: resolve(evidence, "checklist-mobile.png") });
  // A server still exporting the old packet shape fails with an explicit UI
  // message, rather than presenting a stale checklist or crashing the page.
  packetResponse = { ...packet };
  delete packetResponse.prelock_review_checklist;
  await page.getByRole("button", { name: "Prelock review checklist", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "no supported nonbinding checklist" }).waitFor();
  assert.equal(await checklist.count(), 0);
  assert.deepEqual(errors, []);
  assert.ok(calls.every(call => call.method === "GET"), JSON.stringify(calls));
  assert.ok(calls.some(call => call.path === "/api/learning/research/showdown"));
  assert.ok(calls.some(call => call.path.endsWith("/ai-showdown-packet/download")));
  writeFileSync(resolve(evidence, "browser-verification.json"), JSON.stringify({
    passed: true, fixture: "Two-entry display subset of archived Week 4 control; no live solve or selection", requests: calls,
    errors, viewports: [1440, 390], screenshots: ["research-desktop.png", "research-mobile.png", "checklist-desktop.png", "checklist-mobile.png"],
  }, null, 2) + "\n");
  console.log("PASS: Research metadata and frozen prelock checklist visible in actual App at desktop/mobile widths; GET requests only.");
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
