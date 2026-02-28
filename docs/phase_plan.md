# Phase Plan

## Execution Board

### Now
1. Keep `classic` and `showdown` lineup backtests as separate tracks with stable API/UI workflows.
2. Track baseline quality every run:
   - Classic: `slates_completed`, `mean_gap_points`, `worst_case_gap_points`.
   - Showdown: `slates_completed`, `mean_gap_points`, `worst_case_gap_points`.
3. Start showdown captain descriptive research on historical winners:
   - Captain position mix.
   - Captain as top scorer overall vs top scorer on team.
   - Captain archetype performance by spread/total/implied-team-total bands.
   - Status: completed for `draftkings` seasons 2024-2025.
   - Artifacts:
     - `docs/showdown_captain_descriptive_2024_2025.md`
     - `docs/showdown_captain_descriptive_2024_2025.json`

### Next
1. Build matchup-aware captain archetype prediction model for showdown slates.
   - Status: completed (initial v1).
   - Artifacts:
     - `docs/showdown_captain_training_dataset_2024_2025.csv`
     - `docs/showdown_captain_model_2024_2025.json`
     - `docs/showdown_captain_model_eval_2024_2025.json`
     - `docs/showdown_captain_model_eval_2024_2025.md`
2. Add captain archetype probabilities as lineup-construction inputs for showdown generation.
   - Status: completed (captain prior wired into showdown candidate generation and backtests).
   - Code:
     - `backend/app/services/lineup_learning.py`
     - `backend/app/schemas.py`
     - `scripts/run_optimal_vs_predicted_showdown.py`
3. Run walk-forward A/B backtests:
   - Baseline showdown construction vs captain-informed showdown construction.
   - Measure lift in mean gap reduction, top-percentile hit rate, and stability.
   - Status: completed for `draftkings` seasons `2024-2025` at `2,500` lineups/slate.
   - Result snapshot:
     - Baseline mean gap: `56.0362`
     - Captain-informed mean gap: `49.2954`
     - Mean gap lift: `+6.7408` points
     - Win rate across shared slates: `61.54%`
     - Gap stddev reduction (stability lift): `+3.0083`
   - Artifact:
     - `docs/optimal_vs_predicted_showdown_captain_ab_2024_2025.json`
   - Hyperparameter sweep (captain prior strength):
     - Artifact:
       - `docs/showdown_captain_strength_sweep_2024_2025.json`
       - `docs/showdown_captain_strength_sweep_2024_2025.md`
       - `docs/showdown_captain_strength_sweep_2024_2025_2500.json`
       - `docs/showdown_captain_strength_sweep_2024_2025_2500.md`
     - Current best at production scale (`2,500` lineups/slate): `showdown_captain_prior_strength=0.35`.

### Later
1. Extend captain-archetype learning to teammate-context features (who was active/available in-game).
2. Add automated drift monitoring for captain archetype priors by season segment and slate type.
3. Promote the highest-performing lineup policy into production weekly build workflows.

## Phase 1 (Now): Data Foundation
1. Canonical identity tables (`player_master`, `player_alias`, `unresolved_player_queue`).
2. Ingest run lineage (`ingest_run`) and immutable raw snapshots.
3. Curated salary/injury tables with `player_master_id`.
4. Deterministic matching + manual resolve loop.

## Phase 2: Control Plane UI
1. Ingestion job launcher with row-count telemetry and failure logs.
2. Unresolved queue with merge tooling, candidate suggestions, and bulk actions.
3. Data quality dashboard (mapping rate, duplicate rate, stale alias alerts).

## Phase 3: Feature Store + Modeling
1. Time-safe feature generation from historical weeks.
2. Player projection models with uncertainty intervals.
3. Backtesting pipeline with leakage checks and model registry metadata.

## Phase 4: Simulation + Lineup Intelligence
1. Monte Carlo simulations with correlation controls.
2. Lineup-level EV/risk scoring model.
3. Exposure diversification and scenario stress testing tools.

## Future To-Do: Showdown Captain Intelligence
1. Run descriptive analysis on historical showdown winners:
   - Captain position mix (QB/RB/WR/TE/DST).
   - Captain as top scorer overall vs top scorer on captain's team.
   - Captain archetypes by game context (spread, total, implied team totals).
2. Build matchup-aware captain archetype prediction for future schedules:
   - Train on historical showdown slates and outcomes.
   - Predict which captain type is most likely to be optimal for a given matchup.
3. Use predicted captain archetype probabilities to guide lineup generation:
   - Weight captain candidate selection by learned archetype likelihood.
   - Track backtest lift versus baseline showdown lineup construction.
