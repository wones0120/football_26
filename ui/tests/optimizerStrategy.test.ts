import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSIC_GPP_ADVANCED_STRATEGY_ID,
  CLASSIC_GPP_BASELINE_STRATEGY_ID,
  CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
  CLASSIC_LARGE_GPP_STRATEGY_ID,
  CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
  CLASSIC_SMALL_FIELD_CANDIDATE_TARGET,
  SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
  SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
  classicSmallFieldCandidateParams,
  optimizerStrategyId,
} from "../src/optimizerStrategy.ts";

test("uses the explicit versioned strategy for classic GPP", () => {
  assert.equal(
    optimizerStrategyId("classic", "gpp", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    CLASSIC_GPP_ADVANCED_STRATEGY_ID,
  );
  assert.equal(
    optimizerStrategyId("classic", "gpp", CLASSIC_GPP_BASELINE_STRATEGY_ID),
    CLASSIC_GPP_BASELINE_STRATEGY_ID,
  );
});

test("uses the measured Classic pool target for five-lineup Sunday Main", () => {
  assert.deepEqual(classicSmallFieldCandidateParams(false, "SUNDAY_MAIN", 5), {
    classic_candidate_pool_size: CLASSIC_SMALL_FIELD_CANDIDATE_TARGET,
    classic_production_candidate_pool_size: CLASSIC_SMALL_FIELD_CANDIDATE_TARGET,
  });
  assert.deepEqual(classicSmallFieldCandidateParams(true, "SUNDAY_MAIN", 5), {});
  assert.deepEqual(classicSmallFieldCandidateParams(false, "SUNDAY_MAIN", 1), {});
  assert.deepEqual(classicSmallFieldCandidateParams(false, "THURSDAY_NIGHT", 5), {});
});

test("uses distinct explicit classic contest strategies", () => {
  assert.equal(
    optimizerStrategyId("classic", "cash", CLASSIC_HEAD_TO_HEAD_STRATEGY_ID),
    CLASSIC_HEAD_TO_HEAD_STRATEGY_ID,
  );
  assert.equal(
    optimizerStrategyId("classic", "gpp", CLASSIC_LARGE_GPP_STRATEGY_ID),
    CLASSIC_LARGE_GPP_STRATEGY_ID,
  );
  assert.equal(
    optimizerStrategyId("classic", "gpp", CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID),
    CLASSIC_SMALL_FIELD_GPP_STRATEGY_ID,
  );
});

test("uses distinct versioned strategy contracts for showdown cash and GPP", () => {
  assert.equal(
    optimizerStrategyId("showdown", "cash", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    SHOWDOWN_CASH_QB_CAPTAIN_STACK_STRATEGY_ID,
  );
  assert.equal(
    optimizerStrategyId("showdown", "gpp", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    SHOWDOWN_GPP_CAPTAIN_INFORMED_STRATEGY_ID,
  );
});

test("keeps classic cash on its existing strategy input", () => {
  assert.equal(
    optimizerStrategyId("classic", "cash", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    "gpp",
  );
});
