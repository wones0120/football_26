import assert from "node:assert/strict";
import test from "node:test";
import type { SavedContest } from "../src/api.ts";
import { savedContestSummary } from "../src/savedContestSummary.ts";

function contest(facts: Record<string, unknown>): SavedContest {
  return { contest_id: "123", url: "https://www.draftkings.com/draft/contest/123", season: 2026, week: 4,
    slate: "SUNDAY_MAIN", contest_format: "classic", contest_type: "gpp", observation_count: 1,
    latest_contest: { source: "draftkings_embedded_contest_detail", ...facts } };
}

test("ticket payouts identify a satellite even when cataloged as GPP", () => {
  const row = contest({ name: "NFL SUPERSat", capacity: 198, current_entries: 66, maximum_entries: 5,
    entry_fee: 3, prize_pool: 500, source_payload: { contestDetail: {
      payoutSummary: [{ tierPayoutDescriptions: { Ticket: "NFL $20 Millionaire Ticket" } }],
    } } });
  const summary = savedContestSummary(row);
  assert.equal(summary.type, "Ticket satellite");
  assert.equal(summary.entryLimit, "5-max per person");
  assert.equal(summary.capacity, "198");
  assert.equal(summary.entries, "66");
  assert.equal(summary.prizeLabel, "Ticket value");
  assert.equal(summary.prizePool, "$500.00");
});

test("large cash tournament shows capacity separately from per-person limit", () => {
  const summary = savedContestSummary(contest({ name: "NFL $700K Play-Action", capacity: 277447,
    maximum_entries: 20, entry_fee: 3, prize_pool: 700000,
    source_payload: { contestDetail: { IsCashPrizeOnly: true } } }));
  assert.equal(summary.type, "Cash-prize tournament");
  assert.equal(summary.capacity, "277,447");
  assert.equal(summary.entryLimit, "20-max per person");
  assert.equal(summary.entryFee, "$3.00");
  assert.equal(summary.entries, "Unavailable");
});

test("cash formats take precedence over generic cash-prize facts", () => {
  for (const [name, type] of [["NFL Double Up", "Double-up"], ["NFL 50/50", "50/50"], ["NFL Head-to-Head", "Head-to-head"]]) {
    assert.equal(savedContestSummary(contest({ name, source_payload: { contestDetail: { IsCashPrizeOnly: true } } })).type, type);
  }
  assert.equal(savedContestSummary(contest({ name: "NFL Single Entry", maximum_entries: 1 })).entryLimit, "Single entry");
});

test("failed refresh uses one complete older observation and its timestamp", () => {
  const row = contest({ source: "unavailable", error: "Fetch failed", capacity: 200, observed_at: "2026-10-02T14:00:00Z" });
  row.latest_error = "Fetch failed";
  row.latest_successful_contest = { name: "NFL 50/50", capacity: 100, current_entries: 80, maximum_entries: 1,
    entry_fee: 5, observed_at: "2026-10-02T12:00:00Z" };
  const summary = savedContestSummary(row);
  assert.equal(summary.capacity, "100");
  assert.equal(summary.entries, "80");
  assert.equal(summary.type, "50/50");
  assert.equal(summary.snapshotLabel, "Saved snapshot");
  assert.equal(summary.observedAt, "2026-10-02T12:00:00Z");
});

test("partial fresh observation never silently borrows older fields", () => {
  const row = contest({ capacity: 200 });
  row.latest_successful_contest = { capacity: 100, current_entries: 80, maximum_entries: 1 };
  const summary = savedContestSummary(row);
  assert.equal(summary.capacity, "200");
  assert.equal(summary.entries, "Unavailable");
  assert.equal(summary.entryLimit, "Entry limit unavailable");
  assert.equal(summary.snapshotLabel, "Observed");
});

test("missing or invalid facts never become zero or a user-selected GPP type", () => {
  const row = contest({ capacity: "", current_entries: true, entry_fee: -1, maximum_entries: 1.5 });
  const summary = savedContestSummary(row);
  assert.equal(summary.type, "Type unavailable");
  assert.equal(summary.capacity, "Unavailable");
  assert.equal(summary.entries, "Unavailable");
  assert.equal(summary.entryFee, "Unavailable");
  assert.equal(summary.entryLimit, "Entry limit unavailable");
  assert.equal(savedContestSummary(contest({ current_entries: 0, entry_fee: 0 })).entries, "0");
  assert.equal(savedContestSummary(contest({ entry_fee: 0 })).entryFee, "$0.00");
});

test("mixed ticket and cash prizes are not labeled cash-only", () => {
  const summary = savedContestSummary(contest({ source_payload: { contestDetail: {
    payoutDescriptions: { Ticket: "1", Cash: "$100" },
  } } }));
  assert.equal(summary.type, "Ticket + cash prizes");
  assert.equal(summary.prizeLabel, "Total prize value");
});

test("a first failed fetch remains visibly unavailable", () => {
  const summary = savedContestSummary(contest({ source: "unavailable", error: "Fetch failed" }));
  assert.equal(summary.snapshotLabel, "Details unavailable");
  assert.equal(summary.type, "Type unavailable");
  assert.equal(summary.capacity, "Unavailable");
});
