# Agents Guidelines

## Mission
Build a DFS analytics platform that ingests multi-source NFL data, resolves player identity reliably across sources, trains predictive models, simulates outcomes, and supports repeatable lineup research.

## Non-Negotiables
1. Never join player records by raw display name alone.
2. Every ingest run must be traceable, reproducible, and reversible.
3. Raw source files are immutable and versioned by ingest run.
4. Modeling and backtests must be time-safe (no leakage from future data).
5. UI actions must be idempotent and operationally observable.

## System Principles
1. Source-of-truth entity keys over fuzzy joins.
2. Bronze-Silver-Gold data layering:
   - Bronze = raw source snapshots.
   - Silver = normalized, schema-stable tables.
   - Gold = model-ready features and prediction outputs.
3. Event-style lineage for data quality and debugging.
4. Tight feedback loop: detect, explain, and fix unresolved records from UI.

## Canonical Identity Strategy
1. Canonical player key: `player_master_id` (UUID).
2. Alias table stores all known name variants and source IDs.
3. Deterministic matching order:
   - Source native ID match (best).
   - Team + position + normalized name exact match.
   - Rule-based alias match.
   - Human review queue from UI.
4. Any unresolved mapping creates a queue record, never silent drop.
5. Once resolved, mappings are persisted as rules to prevent repeat work.

## Core Data Domains
1. `player_master`: canonical players and stable attributes.
2. `player_alias`: source-specific keys, names, aliases, effective dates.
3. `ingest_run`: metadata for each pipeline execution.
4. `raw_*`: immutable source payload tables.
5. `curated_*`: cleaned normalized facts (salaries, injuries, stats).
6. `features_*`: point-in-time safe training/scoring features.
7. `predictions_*`: model outputs by season/week/slate.
8. `simulations_*`: scenario outcomes and uncertainty outputs.
9. `lineup_*`: generated lineups, exposures, outcomes, audits.

## UI Requirements
1. Professional control plane for:
   - Source uploads and ingestion runs.
   - Match-quality dashboards.
   - Unresolved player review and one-click resolution.
   - Feature build and model run orchestration.
   - Simulation runs and lineup analysis.
2. Every action shows status, logs, row counts, warnings, and errors.
3. Safety rails:
   - Dry-run mode.
   - Confirmation for destructive actions.
   - Retry with idempotency key.

## Modeling Requirements
1. Separate model families:
   - Player fantasy-point projection.
   - Lineup-level expected value and risk.
2. Strict train/validation/test by time window.
3. Backtests must mirror real historical information availability.
4. Include calibration, uncertainty intervals, and drift monitoring.
5. Store model metadata: code version, feature set hash, training window, metrics.

## Simulation Requirements
1. Simulations must incorporate uncertainty distributions, not point estimates only.
2. Allow scenario controls (injury status, pace, weather assumptions).
3. Store seeds and parameters for exact reproducibility.
4. Support both:
   - Historical replay simulations.
   - Future-week scenario simulations.

## Engineering Quality
1. `.env` for local secrets; `.env.example` committed with placeholders.
2. No credentials in code or logs.
3. Migrations required for schema changes.
4. Tests required for:
   - Identity resolution logic.
   - Ingest transforms.
   - Feature leakage checks.
   - API contracts for UI workflows.
5. CI gates: lint, type-check, unit tests, selected integration tests.

## Delivery Workflow
1. Build incrementally in phases:
   - Phase 1: data foundation + identity layer.
   - Phase 2: UI ingest and issue resolution console.
   - Phase 3: modeling + backtesting.
   - Phase 4: simulations + lineup intelligence.
2. Each phase must end with demoable outcomes and acceptance tests.

## Definition of Done
1. Multi-source data can load for a week with deterministic joins.
2. Unmatched records are visible, explainable, and resolvable in UI.
3. Historical backtest pipeline runs end-to-end with reproducible metrics.
4. Future-week projection + lineup analysis can run from the UI.
5. Operational docs and runbooks are up to date.
