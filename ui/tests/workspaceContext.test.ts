import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeSlateId,
  researchSlateId,
  slateContextKey,
  updateRunSelection,
  type PersistedRunSelections,
} from "../src/workspaceContext.ts";

test("normalizes shell and research slate identifiers at the workspace boundary", () => {
  assert.equal(normalizeSlateId(" sunday main "), "SUNDAY_MAIN");
  assert.equal(researchSlateId("SUNDAY_MAIN"), "sunday_main");
});

test("retains persisted run selections independently for each slate scope", () => {
  const sundayMain = { season: 2025, week: 11, slate: "SUNDAY_MAIN" };
  const sundayLate = { season: 2025, week: 11, slate: "SUNDAY_LATE" };
  let selections: PersistedRunSelections = {};

  selections = updateRunSelection(selections, sundayMain, {
    projectionRunId: "projection-main",
    researchSimulationRunId: "simulation-main",
  });
  selections = updateRunSelection(selections, sundayLate, {
    projectionRunId: "projection-late",
  });

  assert.deepEqual(selections[slateContextKey(sundayMain)], {
    projectionRunId: "projection-main",
    researchSimulationRunId: "simulation-main",
  });
  assert.deepEqual(selections[slateContextKey(sundayLate)], {
    projectionRunId: "projection-late",
  });
});

test("treats slate casing as compatible and clears only the requested run type", () => {
  const context = { season: 2025, week: 11, slate: "thursday_night" };
  let selections = updateRunSelection({}, context, {
    projectionRunId: "projection-1",
    optimizerRunId: "optimizer-1",
  });

  selections = updateRunSelection(selections, { ...context, slate: "THURSDAY_NIGHT" }, {
    optimizerRunId: undefined,
  });

  assert.deepEqual(selections[slateContextKey(context)], {
    projectionRunId: "projection-1",
  });
});
