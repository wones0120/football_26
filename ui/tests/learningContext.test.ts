import assert from "node:assert/strict";
import test from "node:test";
import { initialLearningContext, LEARNING_CONTEXT_STORAGE_KEY, parseLearningContext } from "../src/learningContext.ts";
import { ACTIVE_SLATE_CONTEXT_STORAGE_KEY, serializeActiveSlateContext } from "../src/workspaceContext.ts";

test("Learning starts at the live week with all slates and uses separate persistence", () => {
  const active = { season: 2026, week: 6, slate: "THURSDAY_NIGHT" };
  const review = initialLearningContext(active);
  assert.deepEqual(review, { season: 2026, week: 6, slate: "ALL" });
  assert.notEqual(LEARNING_CONTEXT_STORAGE_KEY, ACTIVE_SLATE_CONTEXT_STORAGE_KEY);
  review.week = 5;
  assert.equal(active.week, 6);
  assert.deepEqual(parseLearningContext(serializeActiveSlateContext(review)), review);
});

test("Learning restores custom slate filters and rejects invalid saved context", () => {
  const review = { season: 2025, week: 4, slate: "SUNDAY_LATE_SF_SEA" };
  assert.deepEqual(parseLearningContext(JSON.stringify(review)), review);
  assert.equal(parseLearningContext(null), null);
  assert.equal(parseLearningContext("bad JSON"), null);
  assert.equal(parseLearningContext(JSON.stringify({ ...review, week: 0 })), null);
});
