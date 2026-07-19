# Phase Plan

Last reviewed: 2026-07-19

## Executive Status

1. Phase 1 data foundation and deterministic identity workflows are demoable.
2. Phase 2 control-plane ingestion, unresolved repair, freshness, model defaults, and benchmark visibility are demoable.
3. Phase 3 historical feature, projection, uncertainty, calibration, walk-forward learning, default-off online residual scoring, and rejected game-regime specialist research are implemented and evidence-backed.
4. Phase 4 historical replay, showdown/classic lineup intelligence, exposure controls, pre-lock popularity/duplication proxies, manual role-shock stress tests, 100k candidate research, and durable large-run resume are implemented.

## Execution Board

### Now
1. Keep `classic` and `showdown` lineup backtests as separate tracks with stable API/UI workflows.
2. Track classic/showdown gap metrics, bootstrap intervals, projection interval coverage, and captain-prior drift every recurring benchmark cycle.
3. Preserve current production defaults until broader walk-forward acceptance gates beat them.

### Next
1. Add contest-specific cash/GPP objectives.
2. Add late swap for staggered lock times.

### Later
1. Add point-in-time weather/news shock scenarios.

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
1. Completed: descriptive analysis on historical showdown winners:
   - Captain position mix (QB/RB/WR/TE/DST).
   - Captain as top scorer overall vs top scorer on captain's team.
   - Captain archetypes by game context (spread, total, implied team totals).
2. Completed: matchup-aware captain archetype prediction for future schedules:
   - Train on historical showdown slates and outcomes.
   - Predict which captain type is most likely to be optimal for a given matchup.
3. Completed: predicted captain archetype probabilities guide lineup generation:
   - Weight captain candidate selection by learned archetype likelihood.
   - Track backtest lift versus baseline showdown lineup construction.
4. Completed: salary-relative role archetypes and future-safe total/spread scenario priors:
   - `docs/showdown_captain_scenarios_2024_2025.json`
   - `docs/showdown_captain_scenarios_2024_2025.md`
