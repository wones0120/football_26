import assert from "node:assert/strict";
import test from "node:test";
import { resultCoverage, resultMoney, resultPercent, resultRoi, weeklyResultsForSlate } from "../src/weeklyResultsFormat.ts";
import type { WeeklyResultTotals, WeeklyResultsReport } from "../src/api.ts";

test("weekly formats retain confirmed zero, unknown amounts and weighted ROI", () => {
  assert.equal(resultMoney(0), "$0.00");
  assert.equal(resultMoney(null), "Unknown");
  assert.equal(resultMoney(-19), "-$19.00");
  assert.equal(resultPercent(-19 / 25.5), "-74.51%");
  assert.equal(resultPercent(.25), "25.00%");
  assert.equal(resultPercent(null), "Unknown");
});

test("slate filtering reuses scoped evidence and retains week-wide warnings without mutating the week", () => {
  const monday = { slate: "MONDAY_NIGHT", summary: {
    entries: 5, fees: 7, winnings: null, roi: null, financial_complete_entries: 1,
  }, missing_evidence: ["intent unknown"], contests: [{ entries: [{ entry_id: "a" }, { entry_id: "b" }] }] };
  const custom = { slate: "SUNDAY_LATE_SF_SEA", summary: { entries: 2, fees: 2, winnings: 1.5, roi: -.25 } };
  const report = { summary: { entries: 16 }, slates: [monday, custom], warnings: ["Week coverage unverified"],
    limitations: ["Settlement unknown"], available_weeks: [5, 4] } as unknown as WeeklyResultsReport;
  const before = JSON.stringify(report);
  assert.equal(weeklyResultsForSlate(report, "ALL"), report);
  const filtered = weeklyResultsForSlate(report, "MONDAY_NIGHT");
  assert.equal(filtered.summary, monday.summary);
  assert.equal(resultRoi(filtered.summary), "Unknown");
  assert.deepEqual(filtered.slates, [monday]);
  assert.equal(filtered.slates[0].contests[0].entries.length, 2);
  assert.deepEqual(filtered.warnings, report.warnings);
  assert.deepEqual(filtered.slates[0].missing_evidence, ["intent unknown"]);
  assert.equal(resultRoi(weeklyResultsForSlate(report, "SUNDAY_LATE_SF_SEA").summary), "-25.00%");
  assert.equal(JSON.stringify(report), before);
});

test("a slate without entries has unknown finances rather than confirmed zero", () => {
  const report = { slates: [], summary: { entries: 16 }, warnings: ["Unknown scope"] } as unknown as WeeklyResultsReport;
  const filtered = weeklyResultsForSlate(report, "WEDNESDAY_NIGHT");
  assert.equal(filtered.summary.entries, 0);
  assert.equal(filtered.summary.fees, null);
  assert.equal(filtered.summary.winnings, null);
  assert.equal(resultRoi(filtered.summary), "Unknown");
  assert.deepEqual(filtered.warnings, ["Unknown scope"]);
});

test("zero denominator and partial coverage never display a complete ROI", () => {
  const totals = { entries: 2, fees: 0, winnings: 2, roi: null, financial_complete_entries: 2 } as WeeklyResultTotals;
  assert.equal(resultRoi(totals), "N/A (zero fees)");
  assert.equal(resultCoverage(totals), "2/2 entries with both fee and winnings evidence");
  assert.equal(resultRoi({ ...totals, fees: null }), "Unknown");
  assert.equal(resultRoi({ ...totals, winnings: null }), "Unknown");
  assert.equal(resultRoi({ ...totals, entries: 0, winnings: null }), "Unknown");
});
