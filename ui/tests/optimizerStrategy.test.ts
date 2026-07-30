import assert from "node:assert/strict";
import test from "node:test";

import {
  CLASSIC_GPP_ADVANCED_STRATEGY_ID,
  CLASSIC_GPP_BASELINE_STRATEGY_ID,
  SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
  SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
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

test("uses distinct versioned strategy contracts for showdown cash and GPP", () => {
  assert.equal(
    optimizerStrategyId("showdown", "cash", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    SHOWDOWN_CASH_BASELINE_STRATEGY_ID,
  );
  assert.equal(
    optimizerStrategyId("showdown", "gpp", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    SHOWDOWN_GPP_BASELINE_STRATEGY_ID,
  );
});

test("keeps classic cash on its existing strategy input", () => {
  assert.equal(
    optimizerStrategyId("classic", "cash", CLASSIC_GPP_ADVANCED_STRATEGY_ID),
    "gpp",
  );
});
