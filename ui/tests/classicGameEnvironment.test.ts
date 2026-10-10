import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { gameEnvironmentReviewHtml, RESEARCH_LABEL, HISTORICAL_CONTEXT } from "../src/classicGameEnvironment.ts";
import { singleLineupReportHtml } from "../src/singleLineupReport.ts";
import type { GameEnvironmentReview } from "../src/classicGameEnvironment.ts";
import type { OptimizerResponse } from "../src/api.ts";

const fixture = () => JSON.parse(readFileSync(new URL("../../artifacts/classic_game_environment_review/ui_fixture.json", import.meta.url), "utf8")) as OptimizerResponse;

test("review shows eight offensive slots, sourced ownership and separate DST opponent context", () => {
  const r=fixture(); const html=gameEnvironmentReviewHtml(r.classic_game_environment_review);
  assert.match(html,/Eight offensive slots, including FLEX/);
  assert.match(html,/DST separately/);
  assert.match(html,/opponent implied points/);
  assert.match(html,/Team spread/);
  assert.match(html,/Projected ownership/);
  assert.match(html,/Evidence cutoff/);
  assert.match(html,/tie-aware midrank/);
  assert.match(html,/not lineup targets/);
  assert.match(html,/cash outcomes unavailable/);
  assert.ok(html.includes(RESEARCH_LABEL));
  assert.equal((singleLineupReportHtml(r).match(/<h2>Recommended Classic lineup/g)||[]).length,1);
  assert.equal((singleLineupReportHtml(r).match(/aria-label="Classic Game Environment Review"/g)||[]).length,1);
  assert.ok(!html.includes('<details open'));
});

test("unavailable inputs remain explicit, escaped and informational", () => {
  const r=fixture().classic_game_environment_review!;
  r.rows[0].player='<script>bad</script>';r.rows[0].game_total=null;r.rows[0].projected_ownership=null;
  r.rows[0].tier=null;r.rows[0].availability_reason='<stale>';
  const html=gameEnvironmentReviewHtml(r);
  assert.match(html,/Unavailable/);assert.match(html,/&lt;script&gt;/);assert.match(html,/&lt;stale&gt;/);
  assert.ok(!html.includes('<script>'));
  assert.ok(!/bad lineup|advantage:|disadvantage:|target of three/i.test(html));
});

test("legacy and incompatible review contracts show Unavailable, Captain report remains separate", () => {
  assert.match(gameEnvironmentReviewHtml(null),/Unavailable/);
  const r=fixture();const v={...r.classic_game_environment_review,nonbinding:false} as GameEnvironmentReview;
  assert.match(gameEnvironmentReviewHtml(v),/no supported frozen review/);
  assert.ok(!singleLineupReportHtml({...r,contest_format:'showdown'}).includes('Classic Game Environment Review'));
  assert.equal(singleLineupReportHtml({results:[[{player_id:'legacy'}]]} as unknown as OptimizerResponse),'');
});

test("rendering research leaves optimizer response byte-for-byte unchanged", () => {
  const r=fixture();const before=JSON.stringify(r);
  singleLineupReportHtml(r);gameEnvironmentReviewHtml(r.classic_game_environment_review);
  assert.equal(JSON.stringify(r),before);
  assert.match(HISTORICAL_CONTEXT,/45\.9%.*38\.1%.*16\.0%/);
});
