import assert from "node:assert/strict";
import test from "node:test";
import { captainFamilies, conditionedTotal, teamLimitDescription, exposureWarning, qbLineupLimit, qbCaptainAllowed, qbCaptainDescription, qbCaptainLimitDescription, captainPositionsDescription, showdownPreflightLabel } from "../src/showdownReporting.ts";

test("named Captain exceptions cannot be summarized as a blanket QB ban or permission", () => {
  const report = {allow_qb_captain: false, named_captain_position_exception_ids: ["named-player"]};
  assert.equal(qbCaptainDescription(report), "Named exceptions may qualify");
  assert.equal(qbCaptainLimitDescription(report), "1 if a named QB is eligible");
  for (const override of [{no_qbs: true}, {no_qb_captain: true}]) {
    assert.equal(qbCaptainDescription({...report, ...override}), "No");
    assert.equal(qbCaptainLimitDescription({...report, ...override}), "0");
  }
  assert.match(captainPositionsDescription({allowed_positions: ["WR", "RB"], named_position_exception_ids: ["a", "b"]}), /2 named position exception/);
});

test("Captain position reports honor saved restrictions and effective QB eligibility", () => {
  assert.equal(captainPositionsDescription({allowed_positions: ["WR", "RB", "TE"]}), "Captain positions: WR, RB, TE only");
  assert.equal(captainPositionsDescription({allowed_positions: ["TE"]}), "Captain positions: TE only");
  assert.equal(captainPositionsDescription({allowed_positions: []}), "Captain positions: Any position");
  assert.match(captainPositionsDescription({}), /unavailable/);
  assert.equal(qbCaptainAllowed({allow_qb_captain: false}), false);
  assert.equal(qbCaptainAllowed({no_qb_captain: true}), false);
  assert.equal(qbCaptainAllowed({no_qbs: true,allow_qb_captain: true}), false);
  assert.equal(qbCaptainAllowed({}), true);
});

test("coverage warnings cannot certify Showdown generation readiness", () => {
  assert.equal(showdownPreflightLabel("warn"), "Generation readiness unchecked");
  assert.equal(showdownPreflightLabel("pass", { status: "NOT_READY" }), "Blocked");
  assert.equal(showdownPreflightLabel("pass", { status: "ERROR" }), "Blocked");
  assert.equal(showdownPreflightLabel("fail", { status: "READY" }), "Blocked");
  assert.equal(showdownPreflightLabel("warn", { status: "READY" }), "Saved inputs ready");
});

test("No QBs takes precedence over the other saved QB controls", () => {
  assert.equal(qbLineupLimit({ no_qbs: true, no_two_qbs: true }), 0);
  assert.equal(qbLineupLimit({ no_qbs: true }), 0);
  assert.equal(qbLineupLimit({ no_two_qbs: true }), 1);
  assert.equal(qbLineupLimit({}), 2);
});

test("saved team constraints describe 3 and 4 independently of current controls", () => {
  assert.match(teamLimitDescription({ max_players_per_team: 3 }), /requires 3–3/);
  assert.match(teamLimitDescription({ max_players_per_team: 4 }), /allows 4–2 and 3–3/);
  assert.match(teamLimitDescription({ max_players_per_team: 5 }), /allows 5–1/);
  assert.match(teamLimitDescription({}), /unavailable/);
});

test("requested-count compliance does not conceal underfilled realized exposure", () => {
  const row = { generated_lineups: 4, requested_lineups: 5, configured_cap: .8,
    final_generated_portfolio_exposure: 1, cap_status: "PASS" };
  assert.match(exposureWarning(row)!, /UNDERFILLED PORTFOLIO/);
  assert.equal(exposureWarning({ ...row, generated_lineups: 5, final_generated_portfolio_exposure: .8 }), null);
});

test("family explanation uses the best eligible alternative and its saved blockers", () => {
  const report = { selected_ranks: [], omission_reasons: { "67": "mean short", "68": "player exposure" },
    family_rows: [{ captain_player_id: "rb", reason: "mean short" }],
    ranked_metrics: [
      { captain_player_id: "rb", rank: 67, quality_eligible: false },
      { captain_player_id: "rb", rank: 68, quality_eligible: true, baseline_mean: 102.14 },
    ] };
  const original = JSON.stringify(report);
  const row = captainFamilies(report)[0];
  assert.equal(row.rank, 67);
  assert.equal((row.best_eligible_candidate as Record<string, unknown>).rank, 68);
  assert.equal(row.reason, "player exposure");
  assert.equal(JSON.stringify(report), original);
});

test("conditional values come from saved discovery evidence, with missingness preserved", () => {
  assert.equal(conditionedTotal({ scenario_id: "winner", mean: 100, players:
    Array.from({ length: 6 }, () => ({ adjustment: { scenario_mean: 20 } })) }, "mean"), 120);
  assert.equal(conditionedTotal({ scenario_id: "winner", mean: 100 }, "mean"), null);
  assert.equal(conditionedTotal({ scenario_id: "baseline", mean: 100 }, "mean"), 100);
});
