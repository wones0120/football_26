import assert from "node:assert/strict";
import test from "node:test";
import { candidateIds, parseRecommendation } from "../src/showdownSelectionContracts.ts";
const template = { proposed_candidate_ids: ["run:a", "run:b"], explicitly_considered_ids: ["run:a", "run:b"],
  reasoning: "Two choices", football_theses: ["Script a", "Script b"], complementarity_reason: "Portfolio fit" };
test("exact IDs preserve frozen run and explicit consideration", () => {
  assert.deepEqual(candidateIds("run:a, run:b\nrun:a"), ["run:a", "run:b"]);
  assert.deepEqual(parseRecommendation(JSON.stringify(template), new Set(["run:a", "run:b", "run:c"])), template);
  assert.throws(() => parseRecommendation(JSON.stringify({ ...template, explicitly_considered_ids: [] }), new Set(["run:a", "run:b"])), /explicitly/);
  assert.throws(() => parseRecommendation(JSON.stringify(template), new Set(["other:a", "run:b"])), /frozen run/);
});
test("recommendations cannot fabricate clocks, approval, execution or outcomes", () => {
  for (const extra of [{ decision_timestamp: "prelock" }, { actual_points: 100 }, { status: "ENTERED_CONFIRMED" }, { user_approved: true }]) {
    assert.throws(() => parseRecommendation(JSON.stringify({ ...template, ...extra }), new Set(["run:a", "run:b"])), /template/);
  }
  assert.throws(() => parseRecommendation(JSON.stringify({ ...template, football_theses: ["one"] }), new Set(["run:a", "run:b"])), /theses/);
});
