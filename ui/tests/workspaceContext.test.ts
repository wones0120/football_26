import assert from "node:assert/strict";
import test from "node:test";

import {
  ACTIVE_SLATE_CONTEXT_STORAGE_KEY,
  DEFAULT_SLATE,
  SLATE_OPTIONS,
  normalizeSlateId,
  parsePersistedActiveSlateContext,
  researchSlateId,
  serializeActiveSlateContext,
  slateContextKey,
  updateRunSelection,
  type PersistedRunSelections,
} from "../src/workspaceContext.ts";

test("starts the 2026 Week 1 slate menu with Wednesday night", () => {
  assert.equal(DEFAULT_SLATE, "WEDNESDAY_NIGHT");
  assert.equal(SLATE_OPTIONS[0], DEFAULT_SLATE);
  assert.equal(new Set(SLATE_OPTIONS).size, SLATE_OPTIONS.length);
});

test("normalizes shell and research slate identifiers at the workspace boundary", () => {
  assert.equal(normalizeSlateId(" sunday main "), "SUNDAY_MAIN");
  assert.equal(researchSlateId("SUNDAY_MAIN"), "sunday_main");
});

test("round-trips the active season, week, and slate through browser storage", () => {
  const stored = serializeActiveSlateContext({ season: 2026, week: 2, slate: "sunday main" });

  assert.equal(ACTIVE_SLATE_CONTEXT_STORAGE_KEY, "football-26-active-slate-context");
  assert.deepEqual(parsePersistedActiveSlateContext(stored), {
    season: 2026,
    week: 2,
    slate: "SUNDAY_MAIN",
  });
});

test("rejects malformed or unsupported saved slate contexts", () => {
  assert.equal(parsePersistedActiveSlateContext(null), null);
  assert.equal(parsePersistedActiveSlateContext("not-json"), null);
  assert.equal(parsePersistedActiveSlateContext('{"season":2026,"week":0,"slate":"SUNDAY_MAIN"}'), null);
  assert.equal(parsePersistedActiveSlateContext('{"season":2026,"week":2,"slate":"UNKNOWN"}'), null);
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
