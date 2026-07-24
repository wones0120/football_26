# Target Data Model

> Status: target-schema design contract. Canonical implementation status and priority are tracked in `docs/TODO.md`.

## Purpose

This document defines the target data structure for a neuro-symbolic NFL DFS system built from first principles. It should guide migrations and adapters without being constrained by legacy table names.

The end state is an auditable system where every pregame belief, symbolic rule decision, lineup decision, and postgame result can be replayed and evaluated.

## Design Principles

- Keep raw source data immutable.
- Resolve canonical identities before modeling.
- Store pregame signals as point-in-time snapshots.
- Version every model, rule, projection, and optimizer run.
- Use append-only run tables for learning and evaluation.
- Evaluate all completed games, not only slates that were bet.
- Treat legacy tables as source systems that can feed the target schema through adapters.

## Data Layers

| Layer | Purpose |
| --- | --- |
| Raw ingestion | Preserve source rows/files exactly as received |
| Canonical entities | Stable players, teams, games, and slates |
| Facts and snapshots | Actual outcomes plus point-in-time pregame context |
| Features | Model-ready derived data with build metadata |
| Predictions | Base statistical model outputs |
| Symbolic reasoning | Rule versions, rule applications, and adjusted projections |
| Optimization | Lineups, constraints, exposure, and explanations |
| Learning | Postgame evaluation of projections, rules, and decisions |

## Canonical Entity Tables

### `dim_player`

Canonical player identity.

Required columns:

- `player_id`
- `full_name`
- `first_name`
- `last_name`
- `birth_date`
- `primary_position`
- `created_at`
- `updated_at`

### `player_alias`

Maps provider-specific names and IDs to `dim_player`.

Required columns:

- `alias_id`
- `player_id`
- `source`
- `source_player_id`
- `source_player_name`
- `normalized_name`
- `confidence`
- `created_at`

### `identity_quarantine`

Auditable holding area for source identities that cannot be mapped safely. The
salary adapter repairs only unique, explainable name/team/position matches and
never creates an offensive player identity from salary data alone. Each
unresolved source row is stored with its reason and candidate IDs; optimizer,
projection snapshots, and replay inputs require a canonical player ID and
therefore exclude open quarantine rows.

Required columns:

- `identity_quarantine_id`
- `entity_type`
- `source_schema`, `source_table`, `source_record_key`
- `source_system`, `source_player_key`
- `season`, `week`, `slate`
- `display_name`, `team_id`, `position`
- `reason_code`, `candidate_player_ids`
- `status`, `resolved_player_id`, `resolution_reason`
- `first_seen_at`, `updated_at`, `resolved_at`

### `dim_team`

Canonical team identity by season.

Required columns:

- `team_id`
- `season`
- `team_abbr`
- `team_name`
- `conference`
- `division`

### `dim_game`

One row per NFL game.

Required columns:

- `game_id`
- `season`
- `week`
- `game_date`
- `kickoff_at`
- `home_team_id`
- `away_team_id`
- `roof`
- `surface`
- `neutral_site`

### `dim_slate`

DFS slate definition.

Required columns:

- `slate_id`
- `season`
- `week`
- `site`
- `slate_name`
- `lock_at`
- `created_at`

### `slate_game`

Games included in each slate.

Required columns:

- `slate_id`
- `game_id`

### `slate_player_eligibility`

Player salary and roster eligibility for a slate.

Required columns:

- `slate_id`
- `player_id`
- `site_player_id`
- `salary`
- `roster_position`
- `team_id`
- `opponent_team_id`
- `game_id`
- `as_of`

## Raw Source Tables

Raw tables should be minimally transformed and include source metadata.

Recommended raw tables:

- `raw_weekly_stats`
- `raw_schedules`
- `raw_rosters`
- `raw_injuries`
- `raw_salaries`
- `raw_ownership`
- `raw_vegas_lines`
- `raw_player_props`
- `raw_weather`
- `raw_snap_counts`

Common metadata columns:

- `source`
- `source_file`
- `ingested_at`
- `season`
- `week`
- `raw_payload` where useful

## Actual Result Tables

### `fact_player_game_actual`

Actual player performance for every game.

Required columns:

- `season`
- `week`
- `game_id`
- `player_id`
- `team_id`
- `opponent_team_id`
- `position`
- `dk_points`
- `fd_points`
- `snaps`
- `snap_share`
- `routes`
- `targets`
- `carries`
- `receptions`
- `receiving_yards`
- `rushing_yards`
- `passing_yards`
- `tds`
- `turnovers`

### `fact_dst_game_actual`

Auditable franchise-level defense/special-teams outcomes. The target adapter aggregates nflverse player defense and return components, derives missing game IDs from schedule/team/opponent, normalizes relocation aliases, and uses downloaded DraftKings `fpts` as the exact outcome when available. Reconstructed values remain stored beside the observed override so scoring differences are inspectable.

Required columns:

- `season`, `week`, `game_id`, `player_id`
- `team_id`, `opponent_team_id`, `is_home`
- `sacks`, `interceptions`, `fumble_recoveries`, `safeties`
- `interception_return_tds`, `fumble_return_tds`, `special_teams_tds`
- `blocked_kicks`
- `opponent_score`, `charged_points_allowed`, `points_allowed_score`
- `total_line`, `spread_line`, `opponent_implied_points`
- `reconstructed_dk_points`, `observed_dk_points`, `dk_points`
- `scoring_source`, `created_at`

### `fact_team_game_actual`

Actual team/game context.

Required columns:

- `season`
- `week`
- `game_id`
- `team_id`
- `opponent_team_id`
- `points_for`
- `points_against`
- `plays`
- `pass_attempts`
- `rush_attempts`
- `neutral_pass_rate`
- `pace_seconds_per_play`

### `fact_game_actual`

Actual final game state.

Required columns:

- `game_id`
- `season`
- `week`
- `home_score`
- `away_score`
- `total_points`
- `spread_result`
- `closed_total`
- `closed_spread`

## Pregame Snapshot Tables

Pregame snapshots are point-in-time state. These make historical replay possible.

Recommended snapshot tables:

- `snapshot_injury_status`
- `snapshot_salary`
- `snapshot_ownership_projection`
- `snapshot_vegas_market`
- `snapshot_player_props`
- `snapshot_weather`
- `snapshot_depth_chart`

Common snapshot columns:

- `as_of`
- `source`
- `season`
- `week`
- `game_id`
- `player_id` where applicable

## Feature Tables

### `feature_generation_run`

Metadata for feature builds.

Required columns:

- `feature_run_id`
- `created_at`
- `training_cutoff`
- `source_versions_json`
- `feature_set_hash`
- `status`

### `feature_player_game`

Player-game model features.

Required columns:

- `feature_run_id`
- `season`
- `week`
- `game_id`
- `player_id`
- `feature_json`

### `feature_team_game`

Team-game model features.

Required columns:

- `feature_run_id`
- `season`
- `week`
- `game_id`
- `team_id`
- `feature_json`

### `feature_slate_player`

Slate-specific player features.

Required columns:

- `feature_run_id`
- `slate_id`
- `player_id`
- `salary`
- `ownership_projection`
- `leverage_score`
- `feature_json`

## Prediction Tables

### `model_registry`

Model family and version metadata.

Required columns:

- `model_id`
- `model_name`
- `model_version`
- `trained_on_start`
- `trained_on_end`
- `feature_set_hash`
- `metrics_json`
- `artifact_uri`
- `created_at`

### `model_run`

One execution of a model.

Required columns:

- `model_run_id`
- `model_id`
- `feature_run_id`
- `created_at`
- `data_cutoff_at`
- `params_json`
- `status`

### `projection_run`

Immutable manifest for one completed projection execution. The manifest fixes the model lineage, season/week/slate scope, row count, cutoff, completion status, and creation time independently of the player-level output.

Required columns:

- `projection_run_id`
- `model_run_id`
- `season`
- `week`
- `slate_id`
- `row_count`
- `data_cutoff_at`
- `status`
- `created_at`

### `active_projection_run`

One explicit active-run pointer per season/week/slate. A newly completed prediction run advances its scope atomically; `POST /api/predict/active` can deliberately move the pointer back to an earlier immutable run after validating that the run belongs to the same scope.

Required columns:

- `season`
- `week`
- `slate_id`
- `projection_run_id`
- `selection_reason`
- `selected_at`

### `player_projection`

Append-only player-level output keyed by projection run. Re-running a slate creates a new `projection_run_id`; it does not update or delete earlier player projections. Default application reads use `active_projection_run`, while replay and inspection callers may request an exact run ID.

The active v2 prediction path calibrates these quantiles from weekly walk-forward residuals by position and workload role. Roles such as mobile/pocket QB, lead/committee/receiving RB, and primary/secondary/rotation receiver are derived only from lagged usage features. Sparse roles shrink toward their position parent, and sparse positions shrink toward the global residual distribution. Calibration method, sample sizes, empirical quantile coverage, P10–P90 coverage, MAE, and diagnostic promotion checks are stored in `model_registry.metrics_json` and copied into `model_run.params_json` for the exact run.

DST rows use the `dst_context_v1` component. It blends strictly prior eight-game defense production with what the opponent allowed to other DSTs, combines historical and market-implied points-allowed context, regresses rare return touchdowns and blocks, and shifts calibrated empirical ranges around the context mean. Current-game fantasy outcomes and components are never model inputs.

Required columns:

- `projection_run_id`
- `model_run_id`
- `season`
- `week`
- `game_id`
- `slate_id`
- `player_id`
- `mean`
- `median`
- `p10`
- `p25`
- `p75`
- `p90`
- `stddev`
- `ceiling_prob`
- `calibration_method`
- `calibration_position`
- `calibration_role`
- `calibration_sample_size`
- `created_at`
- `data_cutoff_at`

### `ownership_model_run`

One slate-aware ownership-model execution. The active challenger records its declared feature set, strictly earlier-week training policy, walk-forward MAE, prior-average baseline MAE, rank correlation, classic/showdown slot calibration, and a diagnostic promotion gate in JSON.

Required columns:

- `ownership_run_id`
- `model_id`
- `season`
- `week`
- `slate_id`
- `created_at`
- `data_cutoff_at`
- `training_rows`
- `params_json`
- `metrics_json`
- `status`

### `ownership_projection`

Player/roster-slot ownership output linked to the exact model run. `feature_json` preserves salary/projection ranks, value, slate size, contest format, roster slot, and lagged ownership inputs used for the estimate.

Required columns:

- `ownership_run_id`
- `season`
- `week`
- `slate_id`
- `player_id`
- `roster_position`
- `projected_ownership`
- `created_at`
- `data_cutoff_at`
- `feature_json`

### `simulation_run`

One immutable DT-502 classic-slate simulation manifest. The
`independent_quantile_lineup_v1` contract fixes the exact projection and
available ownership lineage, seed, calibrated marginal sampler, iteration
count, salary/roster contract, cutoff, and completion status. Independent
player marginals are intentional here; shared game states and correlations are
reserved for DT-503.

Required columns:

- `simulation_run_id`
- `simulation_model_id`
- `projection_run_id`
- `ownership_run_id`
- `season`
- `week`
- `slate_id`
- `contest_format`
- `num_simulations`
- `successful_simulations`
- `seed`
- `salary_cap`
- `roster_size`
- `params_json`
- `data_cutoff_at`
- `created_at`
- `status`
- `message`

### `player_simulation`

One player result for an immutable simulation run. Optimal-lineup probability
and field ownership are both percentages; `leverage_score` is their difference
in percentage points. Missing ownership leaves leverage null instead of
reintroducing the retired points-minus-ownership proxy. `result_json` retains
the exact calibrated quantiles, game context, units, and sampling order needed
to replay the seeded pool even if newer salary snapshots arrive later.

Required columns:

- `simulation_run_id`
- `player_id`
- `player_display_name`
- `position`
- `salary`
- `projection_mean`
- `optimal_lineup_count`
- `optimal_lineup_probability`
- `field_ownership`
- `leverage_score`
- `result_json`

## Symbolic Reasoning Tables

### `symbolic_rule`

Stable logical rule identity.

Required columns:

- `rule_id`
- `rule_name`
- `rule_type`
- `created_at`

### `symbolic_rule_version`

Versioned rule condition/action.

Required columns:

- `rule_id`
- `rule_version`
- `enabled`
- `priority`
- `condition_json`
- `action_json`
- `created_at`
- `retired_at`

### `symbolic_rule_run`

One symbolic evaluation run.

Required columns:

- `rule_run_id`
- `projection_run_id`
- `created_at`
- `rules_loaded`
- `rules_applied`
- `status`

### `symbolic_rule_application`

One rule applied to one player/context.

Required columns:

- `rule_run_id`
- `rule_id`
- `rule_version`
- `projection_run_id`
- `player_id`
- `condition_context_json`
- `mean_before`
- `mean_after`
- `p90_before`
- `p90_after`
- `delta_mean`
- `delta_p90`
- `reason`

### `symbolic_adjusted_projection`

Final adjusted projection after symbolic reasoning.

Required columns:

- `rule_run_id`
- `projection_run_id`
- `season`
- `week`
- `game_id`
- `slate_id`
- `player_id`
- `base_mean`
- `adjusted_mean`
- `base_p90`
- `adjusted_p90`
- `reason_json`
- `created_at`

## Human Digital Twin Tables

### `raw_thought_capture`

One immutable record of the user's free-form input exactly as submitted. The
capture stores the requested general, slate, player, or auto context separately
from the raw text so a later extraction policy can be replayed without rewriting
the original thought.

Required columns:

- `capture_id`
- `raw_text`
- `context_type`
- `subject_label`
- `season`
- `week`
- `slate`
- `contest_format`
- `objective`
- `extraction_policy_id`
- `notices_json`
- `source`
- `created_at`

### `raw_thought_candidate`

One immutable draft belief proposed from a capture by the versioned
`raw_thought_extractor_v1` policy. Candidates contain starter scope, posture,
strength, confidence, and extraction rationale for review; they are not beliefs
and cannot affect projections, ownership, exposures, or lineups.

Required columns:

- `candidate_id`
- `capture_id`
- `ordinal`
- `scope_type`
- `subject_label`
- `subject_id`
- `season`
- `week`
- `slate`
- `contest_format`
- `objective`
- `direction`
- `strength`
- `confidence`
- `thought_text`
- `evidence_text`
- `extraction_reason`
- `created_at`

### `raw_thought_candidate_decision`

One immutable acceptance or rejection for a candidate. The unique
`candidate_id` constraint makes the decision final exactly once. Acceptance
stores the complete user-reviewed payload and creates an ordinary
`human_belief` in the same transaction with capture, candidate, and extraction
policy lineage. Rejection preserves the source capture and candidate but creates
no belief.

Required columns:

- `decision_id`
- `candidate_id`
- `decision`
- `belief_id`
- `belief_version_id`
- `reviewed_payload_json`
- `created_at`

### `human_belief`

One immutable row per version of a user-authored belief. `belief_id` identifies
the logical memory; `belief_version_id` identifies the exact historical version.
Revisions, deactivation, and restoration append rows rather than overwriting the
original wording. The current version remains non-operative until an explicit
impact-preview approval is added by `DT-702`.

Required columns:

- `belief_version_id`
- `belief_id`
- `belief_version`
- `supersedes_version_id`
- `operation`
- `status`
- `scope_type`
- `subject_label`
- `subject_id`
- `season`
- `week`
- `slate`
- `contest_format`
- `objective`
- `direction`
- `strength`
- `confidence`
- `thought_text`
- `evidence_text`
- `expires_at`
- `is_retrospective`
- `impact_status`
- `source`
- `metadata_json`
- `created_at`

Supported `scope_type` values are `global`, `contest_profile`, `season`,
`weekly`, `game`, and `player`. Supported operations are `created`, `revised`,
`deactivated`, and `reactivated`. The original `impact_status` field remains part
of the immutable belief version; operative state is derived from the separate
preview and decision records below.

### `belief_impact_preview`

One immutable, player-specific before/after proposal generated by the bounded
`belief_impact_v1` policy. It records the exact belief version, slate context,
base values, proposed values, deltas, modifier, source-run lineage, and safety
notices. It never updates a projection, ownership forecast, or optimizer run.

Required columns:

- `preview_id`
- `belief_version_id`
- `belief_id`
- `policy_id`
- `season`
- `week`
- `slate`
- `contest_format`
- `objective`
- `target_player_id`
- `target_label`
- `adjustment_pct`
- `baseline_json`
- `proposed_json`
- `delta_json`
- `modifier_json`
- `lineage_json`
- `notices_json`
- `created_at`

`belief_impact_v1` scales P10/P50/mean/P90 and suggested exposure by a bounded
direction, conviction, and confidence multiplier. Field ownership remains
unchanged because it estimates other entrants rather than the user's stance.
Missing optimizer exposure stays null. When a matching DT-502 run exists,
optimal-lineup probability is measured for the baseline and replayed with the
same seed and draws after changing only the selected player's distribution.
Without matching simulation lineage, both values stay null rather than using a
fabricated proxy.

### `belief_impact_decision`

One immutable approval or rejection for a preview. The unique `preview_id`
constraint makes each preview final exactly once. An approval copies the exact
proposed modifier into `approved_modifier_json` for the future DT-703 combined
variant; a rejection stores an empty modifier. A preview tied to a superseded,
inactive, or expired belief version cannot be approved. Neither outcome mutates
the base model.

Required columns:

- `decision_id`
- `preview_id`
- `decision`
- `note_text`
- `approved_modifier_json`
- `created_at`

### `digital_twin_variant_set`

One immutable DT-703 comparison bundle for an exact salary-scoped slate,
projection run, and human-decision cutoff. The model projection cutoff and human
decision cutoff remain separate so replay never infers which approvals existed.

Required columns:

- `variant_set_id`
- `policy_id`
- `season`
- `week`
- `slate`
- `contest_format`
- `objective`
- `projection_run_id`
- `projection_data_cutoff_at`
- `decision_cutoff_at`
- `status`
- `created_at`

### `digital_twin_variant`

One of exactly three JSON artifacts in a variant set. `model_only` stores the
unchanged player distribution from the exact projection run. `human_only` stores
only explicitly approved DT-702 modifiers and their belief/preview/decision
lineage; it never copies model projections. `combined` is recomputed by
multiplying the persisted model distribution by those player modifiers. Multiple
approved beliefs for a player compose in deterministic lineage order, while an
unmodified player retains a multiplier of 1.0. Each artifact has a SHA-256 digest
so replay can verify the model and human inputs and the recomputed combined
output without consulting mutable current tables.

Required columns:

- `variant_id`
- `variant_set_id`
- `variant_type`
- `artifact_json`
- `artifact_hash`
- `created_at`

## Agent Feedback Tables

These tables implement the human-in-the-loop process from the Best Ball notes. The agent should ask questions when a prediction or rule looks uncertain, but it should never silently change projections without storing the trigger, answer, and resulting rule.

### `agent_question`

One row each time the agent asks for human judgment.

Required columns:

- `question_id`
- `season`
- `week`
- `slate_id`
- `game_id`
- `player_id`
- `trigger_type`
- `trigger_context_json`
- `question_text`
- `model_run_id`
- `projection_run_id`
- `rule_run_id`
- `asked_at`
- `answered_at`
- `status`

### `human_feedback_event`

Structured record of the answer. This is training data for the later model that predicts which questions are worth asking.

Required columns:

- `feedback_id`
- `question_id`
- `answer_type`
- `answer_text`
- `confidence`
- `recommended_modifier`
- `accepted_modifier`
- `created_at`

Recommended `answer_type` values:

- `approve`
- `reject`
- `adjust`
- `no_change`

### `feedback_training_example`

Derived examples for training a small model that mimics human judgment.

Required columns:

- `training_example_id`
- `question_id`
- `feedback_id`
- `trigger_context_json`
- `answer_type`
- `accepted_modifier`
- `created_at`

## DFS Contest Import Tables

### `source_file_import`

One immutable source-file identity based on the SHA-256 digest of the imported
CSV content. Re-imports can update the observed path and last-ingested time
without changing the identity.

Required columns:

- `source_file_id`
- `source_type`
- `content_sha256`
- `original_path`
- `file_name`
- `file_size_bytes`
- `first_ingested_at`
- `last_ingested_at`
- `metadata_json`

### `dfs_contest`

Normalized contest metadata. When DraftKings does not provide an external
contest ID in the standings export, `contest_id` is deterministically derived
from site, season, week, slate, and source-content hash.

Required columns:

- `contest_id`
- `source_file_id`
- `site`
- `slate_id`
- `season`
- `week`
- `contest_name`
- `contest_format`
- `contest_type`
- `entry_fee`
- `field_size`
- `max_entries_per_user`
- `prize_pool`
- `metadata_json`
- `created_at`
- `updated_at`

`contest_type` is `cash`, `gpp`, or `unknown`. Explicit import metadata wins;
only unambiguous contest-name evidence may infer a type. Generic legacy exports
remain `unknown` so field medians cannot be mislabeled as cash lines.

### `dfs_contest_entry_result`

One normalized standings entry linked to a content-addressed contest and source
file. A complete observed field can support defensible percentile and
field-median comparisons even when the contest type is unknown. Cash-line and
ROI evidence additionally require a verified cash contest and structured payout
tiers.

Required columns:

- `contest_id`
- `entry_id`
- `source_file_id`
- `entry_name`
- `rank`
- `entry_points`
- `lineup_text`
- `ingested_at`
- `created_at`

### `dfs_contest_payout_tier`

Structured cash or ticket awards for a contiguous finishing-rank range.

Required columns:

- `contest_id`
- `min_rank`
- `max_rank`
- `payout`
- `prize_description`
- `created_at`

### `import_batch` and `import_batch_file`

One directory import plus a durable result for every discovered file. File
statuses distinguish imported, deduplicated, skipped, failed, and dry-run
`would_import` outcomes.

### `dk_entry_template_file` and `dk_entry_template_row`

Content-addressed DraftKings entry-template metadata and its original rows.
These are source records only; generated-lineup assignments belong to the
portfolio tables introduced in the next phase.

## Optimization Tables

### `lineup_portfolio`

One named, reloadable set of generated lineups assigned to an imported entry
template. It records optimizer lineage, slate scope, format, and objective.

### `portfolio_lineup`

Ordered lineup membership within a portfolio. A lineup can appear only once in
the same portfolio.

### `contest_entry_assignment`

One paid DraftKings entry mapped to one generated lineup and contest. Unique
constraints prevent the same template row or portfolio lineup from being
assigned twice.

### `dk_upload_export`

An immutable DraftKings upload artifact generated from a portfolio. It stores
the exact CSV content, filename, format, row count, ordered columns, and SHA-256
digest so the downloaded file can be reproduced and audited.

### `dk_export_validation`

An immutable pass/fail report produced before each export attempt. Coded error
rows cover entry mapping, site IDs, salary, roster eligibility, duplicate
players/lineups, template slots, and portfolio exposure. An export artifact is
downloadable only when linked to a passed validation.

### `optimizer_run`

One optimizer execution. For classic cash, `objective_config_json` stores the complete immutable `classic_cash_v1` weights, certainty scale, and fragility penalty rather than only the generic objective name.

Required columns:

- `optimizer_run_id`
- `projection_run_id`
- `rule_run_id`
- `slate_id`
- `season`
- `week`
- `contest_format`
- `objective`
- `strategy`
- `objective_config_json`
- `constraint_config_json`
- `data_cutoff_at`
- `created_at`
- `updated_at`
- `status`
- `message`

### `lineup`

One generated lineup.

Required columns:

- `lineup_id`
- `optimizer_run_id`
- `lineup_number`
- `salary_used`
- `projected_mean`
- `projected_median`
- `projected_floor`
- `projected_p90`
- `objective_score`
- `average_role_certainty`
- `fragility_penalty`
- `ownership_sum`
- `leverage_score`
- `created_at`

### `lineup_player`

Lineup membership. `player_json` retains the player-level cash mean, median, P10 floor, role certainty, fragility, weighted components, penalty, score, and repeated lineup summary when `classic_cash_v1` is active.

Required columns:

- `lineup_id`
- `slot_index`
- `player_id`
- `roster_position`
- `salary`
- `projection`
- `projected_p90`
- `ownership_projection`
- `player_json`

### `lineup_constraint_explanation`

Explainability for lineup construction. Classic cash lineups receive a dedicated `cash_objective` record containing the versioned configuration and aggregate objective terms in addition to the optimizer-configuration record.

Required columns:

- `lineup_id`
- `constraint_name`
- `constraint_status`
- `explanation_json`
- `created_at`

## Best Ball Tables

Best Ball is a draft and portfolio problem, not a one-week lineup optimization problem. Keep it separate from DFS lineup tables.

### `best_ball_contest`

Contest metadata.

Required columns:

- `contest_id`
- `site`
- `contest_name`
- `entry_fee`
- `prize_pool`
- `draft_size`
- `roster_size`
- `advance_structure_json`
- `created_at`

### `best_ball_draft`

One draft room.

Required columns:

- `draft_id`
- `contest_id`
- `draft_started_at`
- `draft_completed_at`
- `draft_position`
- `teams`
- `status`

### `best_ball_pick`

One pick in one draft.

Required columns:

- `draft_id`
- `pick_number`
- `round`
- `round_pick`
- `team_number`
- `player_id`
- `adp_at_pick`
- `picked_at`

### `best_ball_roster`

Final drafted roster.

Required columns:

- `draft_id`
- `player_id`
- `position`
- `team_id`
- `pick_number`
- `round`
- `adp_at_pick`

### `best_ball_weekly_score`

Weekly scoring and auto-started status.

Required columns:

- `draft_id`
- `season`
- `week`
- `player_id`
- `actual_points`
- `auto_started`
- `starter_slot`

### `best_ball_advance_result`

Contest advancement and payout outcome.

Required columns:

- `draft_id`
- `contest_id`
- `regular_season_points`
- `playoff_points`
- `advanced`
- `finish_position`
- `payout`

### `adp_snapshot`

Point-in-time average draft position.

Required columns:

- `snapshot_id`
- `site`
- `contest_type`
- `as_of`
- `player_id`
- `adp`
- `min_pick`
- `max_pick`
- `draft_count`

### `draft_room_state_snapshot`

Optional point-in-time draft room context for future draft assistant work.

Required columns:

- `snapshot_id`
- `draft_id`
- `pick_number`
- `available_players_json`
- `roster_state_json`
- `room_exposure_json`
- `created_at`

## Learning Tables

### `learning_run`

One postgame evaluation batch.

Required columns:

- `learning_run_id`
- `season`
- `week`
- `slate_id`
- `projection_run_id`
- `rule_run_id`
- `optimizer_run_id`
- `created_at`
- `status`
- `recommendations_json`

### `projection_evaluation`

Base projection vs actual result.

Required columns:

- `learning_run_id`
- `projection_run_id`
- `player_id`
- `season`
- `week`
- `game_id`
- `actual_points`
- `projected_mean`
- `projected_p90`
- `absolute_error`
- `squared_error`
- `bias`

### `rule_evaluation`

Rule-adjusted before/after vs actual.

Required columns:

- `learning_run_id`
- `rule_run_id`
- `rule_id`
- `rule_version`
- `player_id`
- `season`
- `week`
- `game_id`
- `position`
- `mean_before`
- `mean_after`
- `actual_points`
- `mae_before`
- `mae_after`
- `improved`
- `delta_mae`

### `optimizer_evaluation`

Lineup and portfolio quality.

Required columns:

- `learning_run_id`
- `optimizer_run_id`
- `lineup_id`
- `actual_points`
- `projected_points`
- `salary_used`
- `ownership_sum`
- `finish_percentile`
- `roi`

### `best_ball_evaluation`

Draft and portfolio quality.

Required columns:

- `learning_run_id`
- `draft_id`
- `contest_id`
- `advance_rate`
- `regular_season_points`
- `playoff_points`
- `stack_count`
- `bring_back_count`
- `adp_value`
- `roster_construction_json`
- `payout`

### `data_quality_run`

One versioned ingestion or readiness audit event.

Required columns:

- `quality_run_id`
- `report_id`
- `contract_id`
- `trigger`
- `season`
- `week`
- `slate`
- `status`
- `score`
- `summary_json`
- `source_context_json`
- `created_at`

### `data_quality_check`

One observed value and declared threshold within a quality run.

Required columns:

- `quality_check_id`
- `quality_run_id`
- `check_id`
- `category`
- `status`
- `severity`
- `table_name`
- `check_name`
- `message`
- `value_json`
- `threshold`
- `affected_scope_json`
- `details_json`
- `created_at`

## Minimum Viable Build Order

1. Canonical identity:
- `dim_player`
- `player_alias`
- `identity_quarantine`
- `dim_game`

2. Actuals and key snapshots:
- `fact_player_game_actual`
- `fact_dst_game_actual`
- `snapshot_salary`
- `snapshot_injury_status`
- `snapshot_vegas_market`

3. Model outputs:
- `feature_generation_run`
- `feature_player_game`
- `model_registry`
- `model_run`
- `projection_run`
- `active_projection_run`
- `player_projection`

4. Symbolic reasoning:
- `symbolic_rule`
- `symbolic_rule_version`
- `symbolic_rule_run`
- `symbolic_rule_application`
- `symbolic_adjusted_projection`

5. Learning:
- `learning_run`
- `projection_evaluation`
- `rule_evaluation`

6. Agent feedback loop:
- `raw_thought_capture`
- `raw_thought_candidate`
- `raw_thought_candidate_decision`
- `agent_question`
- `human_feedback_event`
- `feedback_training_example`

7. DFS contest imports:
- `source_file_import`
- `dfs_contest`
- `dfs_contest_entry_result`
- `dfs_contest_payout_tier`
- `import_batch`
- `import_batch_file`
- `dk_entry_template_file`
- `dk_entry_template_row`

8. Optimization:
- `optimizer_run`
- `lineup`
- `lineup_player`
- `lineup_constraint_explanation`
- `lineup_portfolio`
- `portfolio_lineup`
- `contest_entry_assignment`
- `dk_upload_export`
- `dk_export_validation`

9. Best Ball portfolio:
- `best_ball_contest`
- `best_ball_draft`
- `best_ball_pick`
- `best_ball_roster`
- `best_ball_weekly_score`
- `best_ball_advance_result`
- `adp_snapshot`

## Legacy Adapter Policy

Existing tables should not dictate the final schema. Instead:

- Keep legacy tables as source systems.
- Build adapters that populate the target tables.
- Write target tables into a separate schema such as `target` when legacy `public` tables have name collisions.
- Prefer one canonical target table over multiple near-duplicates.
- Track adapter runs with source table names, row counts, and warnings.

Example mappings:

| Target table | Possible legacy/source tables |
| --- | --- |
| `dim_player` | `player_master` |
| `player_alias` | `player_alias`, `player_mapping_rule` |
| `identity_quarantine` | unresolved `curated_salary` identities |
| `dim_game` | `raw_nfl_schedule`, `raw_schedules` |
| `fact_player_game_actual` | `nfl_weekly_data_with_scores`, `raw_nfl_weekly_stat`, `player_game_feature_matrix` |
| `fact_dst_game_actual` | `raw_nfl_weekly_stat`, `raw_nfl_schedule`, `dk_contest_standings_rows` |
| `snapshot_salary` | `curated_salary`, `curated_salaries`, `raw_salary_row`, `raw_salaries` |
| `snapshot_injury_status` | `curated_injury`, `weekly_injuries`, `raw_injury_row`, `raw_injuries` |
| `feature_player_game` | `player_game_feature_matrix`, `predictive_features` |
| `player_projection` | `player_expected_points` |
| `symbolic_rule` | `symbolic_rules` |
| `symbolic_rule_run` | `symbolic_rule_runs` |
| `symbolic_rule_application` | `symbolic_adjustments` |
| `symbolic_adjusted_projection` | `player_expected_points_adjusted` |
| `learning_run` | `symbolic_learning_runs` |
| `rule_evaluation` | `symbolic_rule_evaluations` |
| `agent_question` | future table; no current equivalent |
| `human_feedback_event` | future table; no current equivalent |
| `best_ball_draft` | future table; no current equivalent |
| `best_ball_pick` | future table; no current equivalent |
| `adp_snapshot` | future table; no current equivalent |
| `lineup` | `actual_top_lineup`, `lineups` |
| `lineup_player` | `actual_top_lineup_player`, `lineup_players` |

## Initial Adapter Command

Run a dry run first:

```bash
.venv/bin/python scripts/apply_target_schema_adapters.py --database football_26_dev --dry-run --pretty
```

Apply into the default `target` schema:

```bash
.venv/bin/python scripts/apply_target_schema_adapters.py --database football_26_dev --pretty
```

The initial adapter covers:

- `dim_player`
- `player_alias`
- `identity_quarantine`
- `dim_team`
- `dim_game`
- `fact_player_game_actual`
- `snapshot_salary`
- `snapshot_injury_status`
