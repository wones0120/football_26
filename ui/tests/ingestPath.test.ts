import assert from "node:assert/strict";
import test from "node:test";

import { resolveCsvIngestPath } from "../src/ingestPath.ts";

test("the NFL folder resolves the selected slate's CSV", () => {
  assert.equal(resolveCsvIngestPath("~/NFL/", "DKSalaries_2026_3_MONDAY_NIGHT.csv"),
    "~/NFL/DKSalaries_2026_3_MONDAY_NIGHT.csv");
});

test("a typed injury filename without .csv is loadable", () => {
  assert.equal(resolveCsvIngestPath("~/NFL/FanDuel_injuries_2026_3_MONDAY_NIGHT",
    "FanDuel_injuries_2026_3_MONDAY_NIGHT.csv"),
  "~/NFL/FanDuel_injuries_2026_3_MONDAY_NIGHT.csv");
});

test("explicit CSV paths are preserved and unsupported extensions are rejected", () => {
  assert.equal(resolveCsvIngestPath(" /tmp/custom.CSV ", "ignored.csv"), "/tmp/custom.CSV");
  assert.equal(resolveCsvIngestPath("", "ignored.csv"), null);
  assert.equal(resolveCsvIngestPath("/tmp/file.xlsx", "ignored.csv"), null);
});

import { injurySourceSlate } from "../src/ingestPath.ts";
test("Sunday Classic subsets share Main injury source and filename", () => {
  for (const slate of ["SUNDAY_EARLY", "sunday_late", "SUNDAY_MAIN"]) {
    assert.equal(injurySourceSlate(slate), "SUNDAY_MAIN");
    assert.equal(resolveCsvIngestPath("~/NFL/", `FanDuel_injuries_2026_5_${injurySourceSlate(slate)}.csv`),
      "~/NFL/FanDuel_injuries_2026_5_SUNDAY_MAIN.csv");
  }
  assert.equal(injurySourceSlate("SUNDAY_NIGHT"), "SUNDAY_NIGHT");
  assert.equal(injurySourceSlate("SUNDAY_MORNING"), "SUNDAY_MORNING");
});
