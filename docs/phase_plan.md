# Phase Plan

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

