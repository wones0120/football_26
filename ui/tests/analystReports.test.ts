import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { filteredReports, selectedReportId, reportApplicationLabel, safeExternalUrl, inlineTokens, parseReportMarkdown, type AnalystReport } from "../src/analystReportLibrary.ts";
const report = (id: string, category: AnalystReport["category"], date: string | null, week = 6): AnalystReport => ({ report_id: id, title: id, category, season: 2026, week, slates: ["SUNDAY_MAIN"], version: "v1", recorded_at: date, preliminary: true, application_status: "research_only", saved_run_ids: [], summary: "Research", available: true });
const reports = [report("old", "briefing", "2026-10-13T00:00:00Z"), report("lineups", "lineup_review", "2026-10-15T00:00:00Z"), report("main", "briefing", "2026-10-14T00:00:00Z"), report("specialist", "specialist", null), report("other-week", "briefing", null, 5)];
test("main briefing comes first, versions remain visible and filters preserve week/slate scope", () => {
  assert.deepEqual(filteredReports(reports, {week:"2026-W6",slate:"SUNDAY_MAIN",category:""}).map(r => r.report_id), ["main","old","specialist","lineups"]);
  assert.equal(filteredReports(reports, {week:"",slate:"THURSDAY_NIGHT",category:""}).length, 0);
  assert.deepEqual(filteredReports(reports, {week:"2026-W5",slate:"",category:"briefing"}).map(r => r.report_id), ["other-week"]);
});
test("selection remains stable until filtering removes it; unavailable reports are not selected", () => {
  assert.equal(selectedReportId(reports, "old"), "old");
  assert.equal(selectedReportId([report("main", "briefing", null)], "old"), "main");
  assert.equal(selectedReportId([{...reports[0],available:false}], null), null);
});
test("research reading never claims an applied run without recorded comparison evidence", () => {
  assert.match(reportApplicationLabel(reports[0]), /not applied/);
  assert.match(reportApplicationLabel({...reports[0],application_status:"saved_run_comparison"}), /listed saved comparison runs/);
  assert.match(reportApplicationLabel({...reports[0],application_status:"unknown"}), /not recorded/);
});
test("Markdown retains headings, tables, citations, lists, code and literal HTML as data", () => {
  const blocks = parseReportMarkdown('# Main\n\n| Player | Cost |\n|---|---:|\n| **A** | $4,800 |\n\n- One\n- Two\n\n1. First\n2. Next\n\n> Unknown\n\n```json\n{"a":1}\n```\n\n<script>alert(1)</script>');
  assert.deepEqual(blocks.map(b => b.kind), ["heading","table","list","list","quote","code","paragraph"]);
  assert.deepEqual(blocks[1], {kind:"table",header:["Player","Cost"],rows:[["**A**","$4,800"]]});
  assert.deepEqual(inlineTokens('**role** [Source](https://nfl.com/news/test) `v1`').filter(t => t.kind !== "text").map(t => t.kind), ["strong","link","code"]);
});
test("unsafe URL schemes and credential URLs cannot become external links", () => {
  for (const link of ["javascript:alert(1)","data:text/html,test","file:///secret","https://name:secret@example.com", "//example.com"]) assert.equal(safeExternalUrl(link), null);
  assert.equal(safeExternalUrl("https://www.nfl.com/news/test"), "https://www.nfl.com/news/test");
});
test("real briefing data parses substantial tables and citations; app navigation points to reader", () => {
  const text = readFileSync(new URL("../../research/wones_football_analyst_20261014_wednesday/v1/WEDNESDAY_BRIEFING.md", import.meta.url), "utf8");
  assert.ok(parseReportMarkdown(text).some(b => b.kind === "table" && b.rows.length === 10));
  assert.ok(inlineTokens(text).some(t => t.kind === "link" && t.target.startsWith("https://")));
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8"), shell = readFileSync(new URL("../src/AppShell.tsx", import.meta.url), "utf8"), reader = readFileSync(new URL("../src/AnalystReports.tsx", import.meta.url), "utf8");
  assert.match(shell, /view: "analyst-reports", label: "Analyst Reports"/); assert.match(app, /viewMode === "analyst-reports"/); assert.match(app, /<AnalystReports \/>/);
  assert.ok(!reader.includes("dangerouslySetInnerHTML")); assert.match(reader, /<AnalystReportMarkdown/);
});

test("actual React Markdown output renders tables/citations and escapes HTML without unsafe links", async () => {
  const { createRequire } = await import("node:module"), { pathToFileURL } = await import("node:url");
  const require = createRequire(import.meta.url), ts = await import("typescript"), React = await import("react"), { renderToStaticMarkup } = await import("react-dom/server");
  const source = readFileSync(new URL("../src/AnalystReportMarkdown.tsx", import.meta.url), "utf8");
  let code = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
  code = code.replaceAll('"react/jsx-runtime"', JSON.stringify(pathToFileURL(require.resolve("react/jsx-runtime")).href)).replaceAll('"react"', JSON.stringify(pathToFileURL(require.resolve("react")).href)).replaceAll('"./analystReportLibrary"', JSON.stringify(new URL("../src/analystReportLibrary.ts", import.meta.url).href));
  const { AnalystReportMarkdown } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
  const html = renderToStaticMarkup(React.createElement(AnalystReportMarkdown, { markdown: '# Safe\n\n| Name | Salary |\n|---|---|\n| **Corum** | $4,800 |\n\n<script>alert(1)</script>\n\n[Source](https://nfl.com/news/report) [Bad](javascript:evil) [Local](receipt.json)\n\n### Lineup 1\n\n### Lineup 1', links: [{target:'receipt.json',kind:'evidence',evidence_id:'receipt'}], onReport: () => {}, onEvidence: () => {} }));
  assert.match(html, /id="lineup-1"/);assert.match(html, /id="lineup-1-1"/);
  assert.match(html, /<table>/); assert.match(html, /<strong>Corum<\/strong>/); assert.match(html, /href="https:\/\/nfl.com\/news\/report"/); assert.match(html, /&lt;script&gt;/); assert.ok(!html.includes('<script>') && !html.includes('href="javascript:')); assert.match(html, /<button[^>]*>Local<\/button>/);
});
