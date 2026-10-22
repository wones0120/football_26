import assert from "node:assert/strict";
import test from "node:test";
import { analystResearchEvidence, analystResearchHtml } from "../src/analystResearchEvidence.ts";
import { buildOptimizerReportHtml } from "../src/optimizerReport.ts";
import type { OptimizerResponse } from "../src/api.ts";

test("legacy/reference checks do not imply authored research or closure", () => {
  assert.equal(analystResearchEvidence(undefined).state, "unrecorded");
  const report = analystResearchEvidence({status:"reference_only",producer_executed:false});
  assert.equal(report.closed,false);
  assert.match(report.lines.join(" "),/Reference evidence only/);
  assert.match(report.lines.join(" "),/does not mean a research worker completed/);
});

test("authored no-change, pending closure, material inputs and actual roster evidence stay distinct", () => {
  const coverage = {status:"mechanisms_current",producer_executed:true,producer_loop_closed:false,
    games:[{game_id:"g",state:"mechanisms_current",authored_assessment:{disposition:"no_change",mechanism:"Supported role unchanged",counterevidence:["Limited snaps"],unknowns:["Final inactives pending"],source_ids:["source1"],authored_at:"2026-10-19T18:00Z"}}]};
  const pending = analystResearchEvidence(coverage);
  assert.match(pending.lines.join(" "),/closure remains pending/);
  assert.match(pending.games[0].details.join(" "),/no numerical scenario change claimed/);
  const material = {...coverage.games[0],authored_assessment:{...coverage.games[0].authored_assessment,disposition:"material"},material_scenario_ids_consumed:["passing"]};
  const receipt = {coverage:{...coverage,producer_loop_closed:true,closure_receipt:{publication_id:"pub",checked_at:"now"}},games:[material],portfolio_dependency:"Shared conditional game worlds, unknown probability"};
  const summary=analystResearchEvidence(receipt,[[{name:"QB",roster_position:"CPT",analyst_research_explanation:{selected_scenario_ids:["passing"],salary:50000,base_mean_sum:80}},{name:"WR",roster_position:"FLEX"}]]);
  assert.equal(summary.closed,true);
  assert.match(summary.games[0].details.join(" "),/does not by itself prove the selected roster changed/);
  assert.deepEqual(summary.rosters[0].names,["CPT: QB","FLEX: WR"]);
  assert.equal(summary.rosters[0].mean,80);
  assert.match(summary.probability,/not calibrated/);
});

test("readable report escapes authored source text and tolerates missing legacy fields", () => {
  const html=analystResearchHtml({status:"mechanisms_partial",games:[{game_id:"<game>",authored_assessment:{mechanism:"<script>bad</script>"}}]});
  assert(!html.includes("<script>"));
  assert(html.includes("&lt;script&gt;"));
  assert.match(html,/partially supported/);
  assert.match(analystResearchHtml(undefined),/Authored research not recorded/);
});

test("non-Analyst count reports omit research section while actual saved Analyst reports show it", () => {
  const base = {job_id:"synthetic-count",status:"completed",contest_format:"showdown",objective:"gpp",enforce_single_te:false,results:[]} as unknown as OptimizerResponse;
  const context = {season:2099,week:1,slate:"SYNTHETIC"};
  assert(!buildOptimizerReportHtml(base,context).includes("Authored football research"));
  const saved = {...base,football_analyst:{status:"completed",research_consumption:{coverage:{status:"reference_only"}}}};
  assert(buildOptimizerReportHtml(saved,context).includes("Reference evidence only"));
});
