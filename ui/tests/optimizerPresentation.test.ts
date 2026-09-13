import assert from "node:assert/strict";
import test from "node:test";

import {
  contextReadinessLabel,
  individualCeilingSummary,
} from "../src/optimizerPresentation.ts";

test("reports context readiness separately from actual adjustments", () => {
  assert.equal(
    contextReadinessLabel({
      context_evaluable_count: 14,
      offensive_player_count: 18,
      market_context_count: 12,
      adjusted_count: 9,
    }),
    "Context-ready: 14/18 · Market-ready: 12 · Adjusted: 9",
  );
  assert.equal(contextReadinessLabel(undefined), "Context readiness: unavailable");
  assert.equal(
    contextReadinessLabel({ scored_count: 7 }),
    "Context-ready: 7 · Market-ready: 0 · Adjusted: 0",
  );
});

test("labels summed player ceilings without claiming a lineup P90", () => {
  assert.deepEqual(
    individualCeilingSummary([{ p90: 20 }, { p90: 18.5 }]),
    { label: "Individual Ceiling Sum", value: 38.5 },
  );
  assert.deepEqual(
    individualCeilingSummary([
      { lineup_ceiling_summary: { value: 41 }, p90: 20 },
      { p90: 18.5 },
    ]),
    { label: "Individual Ceiling Sum", value: 41 },
  );
});
