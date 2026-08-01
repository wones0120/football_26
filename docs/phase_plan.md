# Phase Plan

Last reviewed: 2026-08-01

This is the executive roadmap. `docs/TODO.md` is the authoritative source for
active task status, priority, dependencies, and acceptance checks.

## Executive Status

1. Phase 1 data foundation and deterministic identity workflows are demoable.
2. Phase 2 control-plane ingestion, unresolved repair, freshness, model defaults, and benchmark visibility are demoable.
3. Phase 3 historical feature, projection, uncertainty, calibration, walk-forward learning, default-off online residual scoring, and rejected game-regime specialist research are implemented and evidence-backed.
4. Phase 4 historical replay, showdown/classic lineup intelligence, exposure controls, pre-lock popularity/duplication proxies, manual role and point-in-time weather/news stress tests, contest objectives, deterministic late swap, 100k candidate research, durable large-run resume, and persisted async baseline-versus-shock portfolio runs are implemented.
5. Target-schema governance is migration-authoritative: runtime product services are read-only toward schema, and CI validates the recorded contract for all 57 product tables (`ENG-001`, `MODEL-002`).
6. Long-running work uses a leased standalone worker, and the weekly ingest-to-export decision chain persists eight separately inspectable, resumable checkpoints (`OPS-001`, `OPS-002`).
7. Digital Twin, Models, War Room, Research Lab, Delivery, and Operations share one active slate plus scope-compatible persisted-run selections (`ENG-002`).
8. Classic GPP exposes a persisted versioned strategy choice; the advanced slate-aware engine runs on exact live lineage without silent baseline fallback (`OPT-001`).
9. Showdown cash and GPP have distinct versioned basic-captain contracts; completed lineups, normalized CPT/FLEX slots, failures, and exact run lineage persist and reload (`OPT-002`).
10. Projection champions no longer change when a new run completes. Promotion and rollback require persisted evaluation windows, feature/code hashes, comparable gates, and named approvals (`MODEL-002`).
11. The locked MODEL-001 opportunity/efficiency and DST ablation was rejected on its 2025 W12-W18 holdout; production remains unchanged and the next evaluation requires prospectively captured 2026 evidence.
12. `prospective_source_snapshot_v1` is ready to content-address 2026 DraftKings and nflreadpy observations, preserve server receipt/effective/lock metadata, ingest eligible salaries from the immutable copy, and exclude post-lock files. Real prospective weeks are still required.
13. Participation identity reassessment resolved 399 of 436 roster/snap queue rows through native-ID or unique exact semantic evidence, rebuilt 2013–2025 Silver/Gold data, refreshed the 2024–2025 feature matrix, and retained 37 nondeterministic rows for review.

## Execution Board

### Now
1. Close the remaining one-repository parity gate: the real DraftKings portfolio/export smoke test (`CON-001`). Workspace visual QA (`CON-002`) and fresh-database migration/drift proof (`CON-003`) are complete.
2. Review and checkpoint the consolidation branch, then archive `football_opt` without deleting it (`CON-004`).
3. Keep classic and showdown benchmarks separate, track their declared quality metrics, and preserve current production defaults until a walk-forward acceptance gate beats them.

### Next
1. Capture the first prospective 2026 salary and approved external-source snapshots with provable observation time (`DATA-002`), then rerun the rejected MODEL-001 candidate contract on untouched weeks.
2. Add lock-aware weekly refreshes after the point-in-time source contract is proven (`OPS-003`, `DATA-002`).

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
