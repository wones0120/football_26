import assert from "node:assert/strict";
import test from "node:test";

import type { WeeklyLearningReport } from "../src/api.ts";
import { weeklyLearningReportMarkdown } from "../src/learningExport.ts";

test("ChatGPT export preserves captain weighting, evidence gaps, and full report data", () => {
  const report = {
    report_id: "week-1", contract_id: "weekly_learning_report_v1", builder_version: "v1",
    season: 2026, week: 2, entry_user: "wones0120", generated_at: "2026-09-23T10:00:00Z",
    evidence_hash: "hash-1", status: "partial",
    summary: {
      slates: 1, contests_entered: 1, entries: 1, identity_complete_entries: 1,
      matched_optimizer_entries: 1, entries_with_opt_007: 0, duplicate_entries: 0,
      entry_weighted_projection_observations: 1, entry_weighted_projection_mae: 44.88,
      entry_weighted_projection_rmse: 44.88,
      weekly_stats: { status: "completed", season: 2026, week: 2,
        rows_raw: 600, rows_curated: 600, rows_unresolved: 0,
        snapshot_id: "stats-snapshot", content_sha256: "stats-hash",
        observed_at: "2026-09-23T10:00:00Z", ingest_run_id: "stats-run" },
    },
    slate_reports: [{
      report_id: "slate-1", contract_id: "slate_learning_report_v1", builder_version: "v1",
      season: 2026, week: 2, slate: "SUNDAY_NIGHT", entry_user: "wones0120",
      generated_at: "2026-09-23T10:00:00Z", evidence_hash: "hash-2", status: "partial",
      summary: {
        contests: 1, entries: 1, identity_complete_entries: 1, matched_optimizer_entries: 1,
        entries_with_opt_007: 0, duplicate_entries: 0, projection_player_observations: 1,
        projection_mae: 44.88, projection_rmse: 44.88,
      },
      portfolio_analysis: {}, contests: [{ contest_id: "c1", contest_name: "Sunday | Night" }],
      entries: [{
        contest_id: "c1", entry_id: "e1", rank: 465, field_size: 5945,
        top_percent: 7.82, entry_points: 122.53, projected_points: 85.8,
        lineup_match_basis: "canonical_lineup_signature", identity_complete: true,
        financial: { profit: null },
        players: [{
          roster_position: "CPT", player_display_name: "Davante Adams", player_id: "player-1",
          projected_base_points: 12.58, projected_points: 18.87,
          actual_base_points: 42.5, actual_points: 63.75,
          projection_residual: 44.88, actual_ownership: 21.5,
        }],
      }],
      beliefs: [], agent_questions: [],
      learning_outcomes: {
        beliefs: { total: 0, theses_scored: 0, supported: 0, contradicted: 0, helped: 0,
          hurt: 0, no_measurable_effect: 0, unscored: 0, by_scope: {}, by_confidence_band: {} },
        agent_answers: { total: 0, answered: 0, helped: 0, hurt: 0,
          no_measurable_effect: 0, unscored: 0 }, effect_tolerance_points: 1,
      },
      source_file_ids: ["file-1"], run_ids: { optimizer_run_ids: ["run-1"] },
      missing_evidence: ["lineup:e1:opt_007_control"], interpretation: "Observed outcomes are diagnostic.",
      optimizer_effectiveness: {
        contract_id: "optimizer_effectiveness_v1", best_entered_slate_actual: 122.53,
        unmatched_entered_entries: [], field_benchmarks: {},
        runs: [{ optimizer_run_id: "run-1", status: "incomplete_player_actuals",
          strategy: "showdown_gpp_portfolio_v3", candidate_pool: { status: "original_candidate_pool" },
          generated_count: 10, scored_count: 9, best_generated_actual: 150,
          best_selected_actual: 130, best_entered_actual: 122.53,
          selection_regret_observed: 20, entry_regret_observed: 27.47,
          candidates: [{ pregame: { selector_rank: 4, mean: 100, p90: 160, objective_score: 5 },
            postgame: { actual_points: 150, selected: true, entered: false,
              actual_rank_bounds: [1, 2] } }],
          top_k_capture: { "1": { size: 1, scored: 1, best_scored_actual: 130 } },
          correlations: { objective_score: { n: 9, pearson: 0.1, spearman: 0.2 } },
          field: { c1: { winner: 180, thresholds: { top_1_percent: 160 }, cash_line: null,
            attainment: { top_1_percent: { generated_scored: 0, selected_scored: 0, entered_scored: 0 } } } },
          diagnostic: [{ stage: "CANDIDATE_SELECTION", evidence: "Observed regret 20 points." }],
          missing_actual_player_ids: ["p1"] }],
      },
    }],
    source_file_ids: ["file-1"], run_ids: { optimizer_run_ids: ["run-1"] },
    missing_evidence: ["lineup:e1:opt_007_control"],
    interpretation: "Observed outcomes do not justify model promotion.",
  } satisfies WeeklyLearningReport;

  const markdown = weeklyLearningReportMarkdown(report);
  assert.match(markdown, /CPT \| Davante Adams \| player-1 \| 12\.58 \| 18\.87 \| 42\.50 \| 63\.75 \| 44\.88/);
  assert.match(markdown, /CPT projected and actual columns include the 1\.5 multiplier/);
  assert.match(markdown, /lineup:e1:opt_007_control/);
  assert.match(markdown, /Source file IDs: file-1/);
  assert.match(markdown, /repeated player observations across entries/);
  assert.match(markdown, /Weekly stats records pulled \| 600/);
  assert.match(markdown, /Weekly stats ingest run \| stats-run/);
  assert.match(markdown, /## Optimizer effectiveness/);
  assert.match(markdown, /150\.00 \| 130\.00 \| 122\.53/);
  assert.match(markdown, /1–2 \(bounds\)/);
  assert.match(markdown, /Candidate selection: best selected 130\.00; observed regret 20\.00/);
  const json = markdown.split("~~~~json\n")[1].split("\n~~~~")[0];
  assert.deepEqual(JSON.parse(json), report);

  const compact: WeeklyLearningReport = JSON.parse(JSON.stringify(report));
  compact.contract_id = "weekly_learning_report_v2";
  const effectiveness = compact.slate_reports[0].optimizer_effectiveness!;
  const run = effectiveness.runs[0];
  run.candidate_preview = run.candidates;
  delete run.candidates;
  run.candidate_detail = { url: "/api/learning/reports/slate-1/optimizer-runs/run-1/candidates", evidence_hash: "frozen-hash" };
  effectiveness.inclusion_policy = { policy_id: "entry_linked_and_explicit_diagnostics_v1", included_run_count: 1, excluded_run_count: 9 };
  const compactMarkdown = weeklyLearningReportMarkdown(compact);
  assert.match(compactMarkdown, /frozen-hash/);
  assert.match(compactMarkdown, /\/api\/learning\/reports\/slate-1\/optimizer-runs\/run-1\/candidates/);
  assert.match(compactMarkdown, /150\.00 \| 130\.00 \| 122\.53/);
  assert.match(compactMarkdown, /1 entry-linked or requested diagnostic runs included; 9 unrelated completed runs excluded/);
});
