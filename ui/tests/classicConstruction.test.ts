import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { parseSingleTePreference, constructionValue } from "../src/classicConstruction.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("Single TE keeps existing default and preserves an explicit false", () => {
  for (const value of [null, "", "true", "null", "broken"]) assert.equal(parseSingleTePreference(value), true);
  assert.equal(parseSingleTePreference("false"), false);
});
test("Summary report renders actual composition, limitations, unavailable and distribution", () => {
  const report = { job_id: "synthetic", status: "completed", strategy: "classic_large_gpp_v1",
    strategy_config: {}, contest_format: "classic", objective: "gpp", enforce_single_te: false,
    lineage_persisted: true, results: [],
    construction_summary: { selected_count: 1, definitions: "Counts include DST. Template minimums.",
      research_scope: "Top 10%; 15 contests, 10 slates; three market slates; realized ownership.",
      coverage: "Selected counts are not discovery coverage.", lineups: [{ status: "available", flex_position: "TE",
        composition: { QB: 1, RB: 2, WR: 3, TE: 2, DST: 1 }, qb_pass_catchers: 3 }],
      distributions: { flex_position: { TE: 1 } } },
  } as OptimizerResponse;
  const html = buildOptimizerReportHtml(report, { season: 2000, week: 1, slate: "SUNDAY_MAIN" });
  for (const value of ["TE FLEX permitted, not required", "QB 1", "TE 2", "Same-team WR/TE", "15 contests", "not discovery coverage", "Unavailable"]) assert.ok(html.includes(value), value);
  assert.equal(constructionValue([]), "None");
});
test("Review invocation is a click handler; report loading has no diagnostic request", () => {
  const view = readFileSync(new URL("../src/ClassicConstructionReport.tsx", import.meta.url), "utf8");
  assert.ok(view.includes("onClick={runReview}"));
  assert.ok(!view.includes("useEffect"));
  assert.ok(!readFileSync(new URL("../src/optimizerReport.ts", import.meta.url), "utf8").includes("reviewClassicConstructions("));
  const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.equal((app.match(/enforce_single_te: contestFormat === "classic" && enforceSingleTE/g) ?? []).length, 1);
});
