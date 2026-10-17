import assert from "node:assert/strict";
import test from "node:test";

import {
  availableSlateOptions,
  defaultContestFormatForSlate,
  ACTIVE_SLATE_CONTEXT_STORAGE_KEY,
  RUN_SELECTIONS_STORAGE_KEY,
  parsePersistedRunSelections,
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

test("slate strategy defaults select Classic subsets and Captain single-game slates", () => {
  for (const slate of ["SUNDAY_MAIN", "SUNDAY_EARLY", "SUNDAY_LATE"]) {
    assert.equal(defaultContestFormatForSlate(slate), "classic");
  }
  for (const slate of ["THURSDAY_NIGHT", "SUNDAY_MORNING", " sunday morning ", "SUNDAY_NIGHT", "MONDAY_NIGHT", " sunday night "]) {
    assert.equal(defaultContestFormatForSlate(slate), "showdown");
  }
  for (const slate of ["SUNDAY_MONDAY", "CUSTOM_SLATE"]) {
    assert.equal(defaultContestFormatForSlate(slate), "classic");
  }
});

test("starts the 2026 Week 1 slate menu with Wednesday night", () => {
  assert.equal(DEFAULT_SLATE, "WEDNESDAY_NIGHT");
  assert.equal(SLATE_OPTIONS[0], DEFAULT_SLATE);
  assert.equal(new Set(SLATE_OPTIONS).size, SLATE_OPTIONS.length);
});

test("Sunday Morning is selectable and keeps its runs separate from other Sunday slates", () => {
  assert.ok(availableSlateOptions("SUNDAY_MAIN").includes("SUNDAY_MORNING"));
  const morning = { season: 2026, week: 5, slate: "SUNDAY_MORNING" };
  const main = { ...morning, slate: "SUNDAY_MAIN" };
  const monday = { ...morning, slate: "SUNDAY_MONDAY" };
  let runs = updateRunSelection({}, main, { optimizerRunId: "main" });
  runs = updateRunSelection(runs, monday, { optimizerRunId: "sunday-monday" });
  runs = updateRunSelection(runs, morning, { optimizerRunId: "morning" });
  assert.deepEqual(parsePersistedActiveSlateContext(serializeActiveSlateContext(morning)), morning);
  assert.equal(runs[slateContextKey(main)].optimizerRunId, "main");
  assert.equal(runs[slateContextKey(monday)].optimizerRunId, "sunday-monday");
  assert.equal(parsePersistedRunSelections(JSON.stringify(runs))[slateContextKey(morning)].optimizerRunId, "morning");
});

test("reload restores the optimizer selection by scope before a run completes", () => {
  const selections = updateRunSelection({}, { season: 2026, week: 4, slate: "SUNDAY_MAIN" }, { optimizerRunId: "still-running" });
  assert.equal(RUN_SELECTIONS_STORAGE_KEY, "football-26-run-selections");
  assert.deepEqual(parsePersistedRunSelections(JSON.stringify(selections)), selections);
  assert.deepEqual(parsePersistedRunSelections("invalid"), {});
  assert.deepEqual(parsePersistedRunSelections('["invalid"]'), {});
  assert.deepEqual(parsePersistedRunSelections('{"2026:4:SUNDAY_MAIN":{"optimizerRunId":3,"unknown":"ignore"}}'), { "2026:4:SUNDAY_MAIN": {} });
  assert.deepEqual(parsePersistedRunSelections('{"2026:99:SUNDAY_MAIN":{"optimizerRunId":"bad-scope"}}'), {});
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

test("restores distinct native slate labels on the same day without merging runs", () => {
  const first = { season: 2026, week: 5, slate: "DK_123456" };
  const second = { ...first, slate: "DK_789012" };
  let rows = updateRunSelection({}, first, { optimizerRunId: "captain-first" });
  rows = updateRunSelection(rows, second, { optimizerRunId: "captain-second" });
  assert.deepEqual(parsePersistedRunSelections(JSON.stringify(rows)), rows);
  assert.deepEqual(parsePersistedActiveSlateContext(serializeActiveSlateContext(first)), first);
  assert.equal(parsePersistedActiveSlateContext('{"season":2026,"week":5,"slate":"bad:key"}'), null);
});


test("offers saved contest slates without treating arbitrary labels as prepared evidence", () => {
  const options = availableSlateOptions("SUNDAY_MAIN", ["dk_game_1", "DK_GAME_2", "DK_GAME_1", "bad:key", "UNKNOWN"]);
  assert.ok(options.includes("DK_GAME_1"));
  assert.ok(options.includes("DK_GAME_2"));
  assert.equal(options.filter(value => value === "DK_GAME_1").length, 1);
  assert.ok(!options.includes("BAD:KEY"));
  assert.ok(!options.includes("UNKNOWN"));
});
