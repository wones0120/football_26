# Agents Guidelines

## Mission
Build a DFS analytics platform that ingests multi-source NFL data, resolves player identity reliably across sources, trains predictive models, simulates outcomes, and supports repeatable lineup research.

## Non-Negotiables
1. Never join player records by raw display name alone.
2. Every ingest run must be traceable, reproducible, and reversible.
3. Raw source files are immutable and versioned by ingest run.
4. Modeling and backtests must be time-safe (no leakage from future data).
5. UI actions must be idempotent and operationally observable.
6. Model truth and user preferences are separate. User constraints may change optimizer eligibility or selection, but must never alter projections, football context, ownership, or historical validation. Every user-driven exclusion must retain its model assessment and carry an explicit user-preference reason in optimizer reports.

## System Principles
1. Source-of-truth entity keys over fuzzy joins.
2. Bronze-Silver-Gold data layering:
   - Bronze = raw source snapshots.
   - Silver = normalized, schema-stable tables.
   - Gold = model-ready features and prediction outputs.
3. Event-style lineage for data quality and debugging.
4. Tight feedback loop: detect, explain, and fix unresolved records from UI.

## Football Awareness First
Football realism is the primary domain acceptance criterion for projections, simulations, Analyst research, optimization and lineup recommendations. Mathematical validity or a higher objective alone does not make a result suitable for use. Read and apply [the football-awareness review](skills/football-awareness/SKILL.md) for those tasks; ordinary UI/import maintenance need not invent football analysis.

- Explain how the complete lineup succeeds through plausible game outcomes, roles and shared opportunities, and compare credible alternatives and salary tradeoffs.
- Reject methods that violate football mechanics, double-count opportunities, suppress legitimate individual upside or depend on unsupported role assumptions. Diagnose the cause instead of adding arbitrary penalties or teammate limits.
- Distinguish a plausible story from its probability. Use calibrated evidence where available; label unknown likelihood and conditional Analyst judgments without invented percentages. Unusual outcomes are not automatically implausible.
- Football reasoning and empirical validation must agree before promotion. Do not override measured evidence with reputation, hindsight or an attractive narrative; document contradictions and test them. Preserve user preferences separately from model truth and preserve explicitly requested baseline objectives as comparisons.
- Apply this review before recommendations or activation, and expose material assumptions in the app/report workflow. A dormant report or passing code tests alone does not establish a football-valid model.

## Evidence and Experiments
1. Intended assignment, exported artifact, and observed contest entry are separate evidence states. Preserve their source identifiers, timestamps, and linkage independently.
2. Compare rosters using canonical player identity and format-relevant roles, including Showdown Captain identity. Roster equality alone does not prove unique origin, submission intent, or timing. Preserve ambiguous matches and missing evidence explicitly; do not pick a newest run as proven origin.
3. Preserve original historical evidence. Corrections and new evaluations create separately identified records with lineage; reconstructed inputs must not be presented as original snapshots.
4. Historical evaluations identify the scoring definition/version and retain evidence that inputs were available before the applicable decision and lock times. A stored cutoff alone is insufficient proof; missing chronology remains explicit.
5. Preserve candidate variants and report distinct canonical roster counts separately. Candidate identity, saved lineup identity, generation order, and selector rank are not interchangeable.
6. Disclose previously inspected outcomes as retrospective evidence. Freezing a later analysis does not restore outcome blindness or create fresh held-out validation.
7. Controlled selector comparisons use the same frozen candidate pool, inputs, seed, and constraints except for the declared treatment. Identify generation experiments separately and report pool changes. Record requested and achieved portfolio size, solver status, and infeasibility; report any constraint relaxation as a separate comparison.

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
   - Payload-aware retries: the same scoped idempotency key and equivalent semantic payload return the original result; changed assignment or export content under that key is rejected explicitly. Preserve the original artifact and receipt.

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
5. Current application CI runs Python compilation and tests, UI tests, and the TypeScript/Vite build. Schema CI runs migration and drift checks for affected paths. Distinguish desired gates from implemented checks.

## Working Tree and Validation
1. Before editing, inspect working-tree status and relevant existing changes. Preserve pre-existing modified and untracked work; do not revert, overwrite, delete, or attribute unrelated changes to the task. Review task changes against that baseline; clarify only when overlap cannot be reconciled safely.
2. Start with affected tests; broaden validation only for a scope or regression reason. Inspect service/database prerequisites and output destinations first, use isolated fixtures or a test database for mutation checks, and preserve existing artifacts. Report missing prerequisites and skipped checks accurately.
3. Verified local command patterns from the repository root:
   - Backend: `PYTHONPATH=. .venv/bin/python -m pytest <affected-test-path> -q` with the local Python environment installed.
   - UI unit tests: `node --experimental-strip-types --test ui/tests/<affected>.test.ts` with a supported Node runtime (CI uses Node 22).
   - UI type-check/build when warranted: `npm --prefix ui run build` with UI dependencies installed.
4. Browser checks require their documented browser, Playwright, and fixture prerequisites; inspect each script's artifact paths before running. Source inspection alone is not visual validation.

## Model efficiency

Follow the global Model selection and efficiency guidance; this repository does not define a separate model ladder. Explicit user model choices take precedence. Do not infer model generation from an unqualified family name or switch models silently.

## Delivery Workflow
Delivery phases and the platform Definition of Done below are roadmap milestones. Individual tasks complete against their requested scope, relevant regression checks, and affected operational documentation. The identity, ingest, leakage, and API test requirements apply when those behaviors change.

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
