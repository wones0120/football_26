# Neuro-Symbolic Upgrade Roadmap

> Status: area-specific architecture reference. Canonical implementation status and priority are tracked in `docs/TODO.md`.

## Current Baseline

The repo already has strong building blocks:

- Neural/statistical component:
  - `predictive_features` table generation in `Database/features.py`
  - Gradient boosting projections in `backend/services/predictions.py`
- Symbolic component:
  - Explicit lineup constraints in `backend/services/optimizer.py` and `backend/services/gpp_optimizer.py`
  - Rule-style post-model adjustments in `backend/services/agent.py`
- Data foundation:
  - raw -> curated ingest with `player_master_id` mapping in `Database/curated_ingest.py`

The main gap is orchestration: symbolic reasoning is mostly separate from model training/inference and lacks a shared, versioned rule system.

## Target Neuro-Symbolic Architecture

Use three layers with explicit contracts:

1. Learned layer (neural/statistical)
- Produce calibrated player outcome distributions:
  - mean, floor, ceiling, uncertainty.
- Continue writing to `player_expected_points`.

2. Symbolic reasoning layer
- Evaluate explicit rules against model outputs and context:
  - injury gating,
  - pace/funnel adjustments,
  - stack viability checks,
  - lineup legality + contest-style constraints.
- Store each rule activation and adjustment with reason codes.

3. Decision layer
- Build lineups from the adjusted distribution with solver constraints.
- Return explainable artifacts:
  - "why player was boosted/filtered",
  - "which lineup constraints bound the solution."

## Data Model Additions (Recommended)

Add these tables:

- `symbolic_rules`
  - rule_id, rule_name, version, enabled, condition_json, action_json.
- `symbolic_adjustments`
  - season, week, slate, player_id, rule_id, delta_mean, delta_p90, reason.
- `symbolic_projection_snapshots`
  - rule_run_id, season, week, slate, player_id, base_mean, adjusted_mean, base_p90, adjusted_p90, rule_ids, data_cutoff_at.
- `symbolic_rule_evaluations`
  - learning_run_id, rule_run_id, rule_id, rule_version, season, week, player_id, mean_before, mean_after, actual_points, mae_before, mae_after, improved, delta_mae.
- `symbolic_learning_runs`
  - learning_run_id, season, week, rule_run_id, aggregate MAE/hit-rate metrics, recommendations_json.
- `model_registry`
  - model_name, version, feature_set_hash, trained_on_range, metrics_json.
- `lineup_explanations`
  - job_id, lineup_idx, explanation_json, constraint_summary_json.

These additions keep the system auditable and reversible.

## Phased Implementation

### Phase 1: Rule Engine Foundation

- Move hard-coded logic from `backend/services/agent.py` into rule records.
- Add rule evaluation service:
  - input: projection rows + feature context + injuries,
  - output: adjusted rows + explanation rows.
- Persist adjustments to `symbolic_adjustments`.

### Phase 2: Distribution-Aware Optimization

- Extend predictions to persist uncertainty fields consistently.
- Update optimizer objective to consume uncertainty and leverage terms from adjusted values.
- Persist lineup explanations.

### Phase 3: Closed-Loop Learning

- After each completed slate, compare projected vs. realized outcomes.
- Track which symbolic rules improved or hurt calibration.
- Reweight or disable low-performing rules automatically behind safeguards.
- Persist the weekly evaluation with `POST /api/agent/learning/evaluate` after actuals are loaded, even for games/slates that were not bet.
- Backfill historical weeks with `.venv/bin/python scripts/backfill_symbolic_learning.py`, starting with `--dry-run` to inspect missing projections and already-evaluated weeks.
- Treat recommendations as review inputs first; do not auto-disable or retune rules until enough rows accumulate by rule/position/team.
- Use `.venv/bin/python scripts/report_target_rule_learning.py --database football_26_dev --through-season 2025 --through-week <N> --pretty` to inspect what the target-native rule learner would know at any replay point in the 2025 season.
- Use `.venv/bin/python scripts/replay_target_rule_evolution.py --database football_26_dev --season 2025 --pretty` to walk the season and see the recommendation state entering each week.
- Use `.venv/bin/python scripts/simulate_target_policy_replay.py --database football_26_dev --season 2025 --pretty` to compare baseline, static symbolic, and evolving symbolic policy performance without mutating live rule versions.
- Use `--contest-profile cash` or `--contest-profile gpp` on the report/replay scripts to separate floor/median rules from tournament-upside rules. Cash should continue to optimize projection error and floor stability; GPP needs additional ceiling, ownership, and correlation metrics before it should drive real staking decisions.
- Use `.venv/bin/python scripts/report_target_gpp_learning.py --database football_26_dev --pretty` to score GPP-tagged rules on spike outcomes, top-week outcomes, and salary value. DraftKings contest standings exports can now be loaded from the UI ownership controls to populate `dk_ownership`; correlation and full portfolio outcome data remain the larger GPP gaps.
- Use `.venv/bin/python scripts/report_lineup_ownership_templates.py --database football_26_dev --season 2025 --pretty` to summarize high-finishing lineup ownership templates. Keep classic and showdown/captain templates separate because their ownership structures are materially different.
- Use `.venv/bin/python scripts/replay_lineup_template_fit.py --database football_26_dev --season 2025 --slate SUNDAY_MAIN --pretty` to test whether the classic ownership-template policy is enriched in top-percentile finishes before converting it into hard optimizer constraints.

### Phase 4: Human Feedback Agent

- Add `agent_question` and `human_feedback_event` tables.
- Ask for human review only when the model/rule layer detects uncertainty, stale context, or conflicting signals.
- Save every trigger, question, answer, and accepted modifier.
- Treat `no_change` answers as real labels, not empty outcomes.
- Convert accepted answers into expiring symbolic rule versions.
- Train a small feedback model later to predict easy human answers and reduce unnecessary questions.

### Phase 5: Best Ball Portfolio Layer

- Keep Best Ball separate from weekly DFS optimization.
- Add draft, pick, roster, ADP, weekly score, and advancement tables.
- Evaluate roster construction, stack/bring-back structure, ADP value, playoff-week correlation, advance rate, and payout.
- Use Best Ball outcomes to improve draft/portfolio rules rather than one-week lineup rules.

## Immediate High-Impact Changes

1. Replace static `AgentConfig` constants with table-driven rules.
2. Add a "reason trace" payload to `/api/agent/run` and optimizer outputs.
3. Enforce model/rule version stamping on each prediction run.
4. Persist closed-loop learning outputs after every completed week:
- projection snapshots,
- per-rule evaluation rows,
- learning-run recommendations.
5. Add human-feedback audit tables:
- `agent_question`,
- `human_feedback_event`,
- expiring rules generated from accepted feedback.
6. Add Best Ball portfolio tables:
- draft room state,
- picks,
- rosters,
- ADP snapshots,
- weekly auto-start results,
- advance/payout results.
7. Add regression tests for:
- no-rule baseline,
- injury out-rule,
- pace/funnel matchup rule,
- lineup legality under adjusted pools.

## Additional Data Suggestions

Prioritize data that adds signal beyond current weekly aggregates:

1. Snap and route participation by game/week
- Improves role stability for WR/TE/RB projection.

2. Vegas props and line movement history
- Strong prior for touchdown/yardage distributions and game environment shifts.

3. Weather and stadium conditions (hourly, game-time aligned)
- High impact for passing efficiency and kicker/DST outcomes.

4. Offensive line and defensive line injury status
- Better sack-pressure and run-efficiency modeling.

5. Play-by-play expected points and success rates
- Enables richer team-context and red-zone feature generation.

6. Contest-level DFS ownership and payout outcomes
- Improves leverage modeling and portfolio utility optimization.
- Start with downloaded DraftKings `contest-standings-*.csv` or `.zip` files. Loading them creates raw contest player rows, contest entries, and `dk_ownership` rows that the optimizer can use immediately.

## Integration Notes

- Land new feeds first in `raw_*` tables, then curated mappings with `player_master_id`.
- Keep season/week/slate keys consistent across all new tables.
- Backfill incrementally per season to avoid long blocking migrations.
- Use `docs/target_data_model.md` as the schema contract and `scripts/inspect_schema_readiness.py` to classify each database as target-ready, legacy-mappable, or missing required learning tables.
