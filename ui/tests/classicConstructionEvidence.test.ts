import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { lowerConcentrationEvidenceHtml, constructionReviewExportHtml, LOWER_CONCENTRATION_LABEL } from "../src/classicConstructionEvidence.ts";

const captured = JSON.parse(readFileSync(new URL("../../artifacts/classic_construction_review_live_fix/live-review-response.json", import.meta.url), "utf8"));
test("Captured validated alternative exposes nine exact players, swaps, scope and frozen risk in UI and export without modifying evidence", () => {
  const before = JSON.stringify(captured);
  const html = lowerConcentrationEvidenceHtml(captured);
  for (const value of [LOWER_CONCENTRATION_LABEL, "5.328972", "130.064739", "231.298675", "$49800", "Added: Cade Otton", "Removed: Brenton Strange", "implementation_matches_saved=false", "Saved team cap 4", "Elevated (frozen)", "Portfolio validation: verified", "Leverage: UNAVAILABLE; ownership-chalk: DISABLED; duplication: DISABLED"]) assert.ok(html.includes(value), value);
  const result = captured.comparisons.find((r: any) => r.family === "QB + two WR/TE + one offensive bring-back").replacement;
  assert.equal(result.roster.length, 9);
  assert.equal(result.construction.qb_team_offense_including_qb, 3);
  assert.equal(result.construction.qb_game_all_players, 4);
  for (const value of ["Tee Higgins → Chase Brown", "Salary change $0", "2.599408", "4.594135", "-0.006013", "Offensive RB bring-back: Chase Brown", "zero remaining appearance budget"]) assert.ok(html.includes(value), value);
  for (const p of result.roster) assert.ok(html.includes(p.player_id), p.name);
  assert.ok(constructionReviewExportHtml(captured).includes(html));
  assert.equal(JSON.stringify(captured), before);
});
test("Unvalidated or nonreducing alternatives receive no validated lower-concentration label; missing risk stays unavailable and HTML is escaped", () => {
  const copy = structuredClone(captured);
  const result = copy.comparisons.find((r: any) => r.family === "QB + two WR/TE + one offensive bring-back").replacement;
  result.portfolio_validation.status = "failed";
  assert.equal(lowerConcentrationEvidenceHtml(copy), "");
  result.portfolio_validation.status = "verified";
  result.construction.max_team_all = 4;
  assert.equal(lowerConcentrationEvidenceHtml(copy), "");
  result.construction.max_team_all = 3;
  delete copy.active_constraints.elevated_player_ids;
  result.roster[0].name = '<script>alert("x")</script>';
  const html = lowerConcentrationEvidenceHtml(copy);
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(!html.includes("Elevated (frozen)"));
});
