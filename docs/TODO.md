# Football_26 TODO Backlog

Last updated: 2026-07-18

## Completed Baseline (Reference)
- [x] Showdown captain descriptive analysis completed for 2024-2025.
- [x] Showdown captain archetype model v1 trained and evaluated.
- [x] Showdown captain-informed A/B backtest implemented and validated.
- [x] Showdown captain strength sweep completed; production default is `0.35` at `2,500` lineups/slate.
- [x] Main-slate value-driver analysis completed (positions, O/U, spread, FLEX tendencies).
- [x] Combined professional report generated for showdown + regular slates.

## Next Session Runbook (Execute In Order)
- [x] Task 1: Productionize showdown defaults.
  - Goal: no manual model path/strength entry required in normal runs.
  - Deliverable:
    - config keys for `showdown_captain_model_path` and `showdown_captain_prior_strength`.
    - UI uses defaults automatically, with override controls.
  - Acceptance:
    - running showdown backtest from UI with defaults produces captain-informed mode at `0.35`.
- [x] Task 2: Add benchmark suite command.
  - Goal: one command runs full recurring benchmark stack.
  - Deliverable:
    - script that runs classic backtest, showdown baseline, showdown captain-informed, and main-slate analysis.
    - writes results into dated folder `docs/benchmarks/<timestamp>/`.
  - Acceptance:
    - one command returns non-empty output folder with all JSON + summary markdown.
- [x] Task 3: Add benchmark delta comparison.
  - Goal: quickly determine whether model quality improved or regressed.
  - Deliverable:
    - script that compares latest benchmark folder to previous folder.
    - outputs change report for mean/median gaps, win rates, and stability.
  - Acceptance:
    - markdown delta report generated with clear up/down indicators.
- [x] Task 4: Wire reports into UI.
  - Goal: consume analysis without leaving control plane.
  - Deliverable:
    - UI section listing latest generated reports (main slate, showdown, combined).
    - click to open/download artifacts.
  - Acceptance:
    - no manual filesystem navigation needed to access current reports.

## P0 - Resume First
- [x] Finalize default showdown captain settings in product flows (`model_path`, `prior_strength=0.35`) and expose as saved presets.
- [x] Add one-click UI action to run the combined showdown + classic benchmark suite and write timestamped artifacts.
- [x] Add a single "Current Model Card" view in UI (data range, slates, key metrics, best params, artifact links).

## P0 - Data Integrity and Coverage
- [x] Add ingestion validation gates: enforce required columns, type checks, duplicate checks per file before write.
- [x] Add DST-specific identity pipeline rules (team defense aliases, no player-name matching fallback for DST).
- [x] Add automated unresolved-queue triage reports (new unresolveds by source/week/slate).
- [x] Add data freshness checks for salaries/injuries/schedules/stats with UI status badges.

## P0 - Evaluation Framework
- [x] Create a canonical benchmark command that runs:
  - classic optimal-vs-predicted
  - showdown baseline
  - showdown captain-informed
  - main-slate value-driver refresh
- [x] Save benchmark outputs under dated folders and compare against previous run with delta tables.
- [x] Add confidence intervals / bootstrap error bars for gap metrics and win-rate metrics.

## P1 - Main Slate Modeling (Classic)
- [x] Convert main-slate value-driver findings into learned features used by lineup scoring.
- [x] Add game-environment features for classic lineups:
  - team implied totals
  - game totals
  - spread context
  - opponent-adjusted matchup features
- [x] Add ablation tests for classic lineup scoring to measure feature contribution.
- [x] Add classic parameter sweep (candidate lineups per slate, training windows, thresholds) and persist best config.

## P1 - Showdown Modeling
- [x] Retire historical injury reports as a dependency; keep the rejected injury-based candidate documented but off the critical path.
- [x] Add injury-free usage-weighted roster continuity from prior carries/targets and the current salary pool.
  - Evidence: with unresolved salary players included in identity coverage, continuity scored `27.3%` top-1 / `51.5%` top-2 versus baseline `33.3%` / `57.6%` across 33 evaluated slates; not promoted.
- [x] Add season-segment drift checks and automatic alerts when captain priors shift materially.
- [x] Extend captain modeling beyond position class with salary-relative `premium`, `core`, and `value` role buckets within position.
- [x] Add showdown scenario analysis module:
  - which captain archetypes win by matchup/game context
  - descriptive and predictive views for future slates
  - Evidence: `docs/showdown_captain_scenarios_2024_2025.{json,md}` contains 41-slate role distributions and sample-gated, Laplace-smoothed future-safe scenario priors.

## P1 - Player Projection Engine
- [x] Implement opponent-specific player scoring distributions (player-vs-opponent history plus rolling defense-by-position mean and p90 context).
- [x] Add teammate-on/off context features (player injury status, team skill-position outs, same-position outs, and usage multipliers).
- [x] Train and compare model families (rolling baseline, ridge linear, regression tree, and shallow neural net) under strict whole-week time-split validation.
  - Evidence: `docs/projection_model_family_comparison_2024_2025.{json,md}`; the validation-selected tree achieved `2.610` MAE on the untouched 2025 W12-W18 test window. Production was not automatically changed.
- [x] Calibrate uncertainty (mean, p75, p90, p95, and 25+ point tail risk) and track calibration drift.
  - Evidence: `docs/projection_calibration_drift_2024_2025.{json,md}` covers 15/15 Sunday-main slates and 2,856 players with no configured alerts.

## P1 - Lineup Generator and Policy Learning
- [x] Build policy-learning loop from historical actual top lineups (top-k per slate) into lineup scoring.
- [x] Add salary-structure priors, learned player/QB/DST exposure caps, and correlation/anti-correlation controls.
- [x] Retire observed historical ownership as a dependency; do not substitute realized outcomes.
- [ ] Add a clearly named pre-lock `popularity_proxy` and lineup duplication-risk score from salary, projection, value, game environment, and generated-lineup concentration.
- [x] Add robust validity checks for every generated candidate and selected lineup with hard-fail violation details.
- [x] Support 100k+ candidate experiments with deterministic seeds (request default `100000`, maximum `500000`).
- [ ] Add interrupted-run checkpoint/resume support for 100k+ candidate experiments.

## P2 - UI / Control Plane
- [x] Add dedicated "Analysis" area for generated reports (showdown, main slate, combined).
- [x] Add run history explorer with filters (source, season range, slate type, model config).
- [ ] Add expandable/collapsible sections for all heavy tables by default (ingest queues, coverage, recent runs, and benchmark history default collapsed; simulation/backtest result tables remain).
- [x] Add export bundle action (JSON + MD report + config snapshot).

## P2 - Ops / Engineering
- [ ] Add integration tests for ingestion->curation->backtest critical path.
- [ ] Add migration smoke test and schema drift checker in CI.
- [x] Add runbook for full environment bootstrap from empty database (`docs/BOOTSTRAP_RUNBOOK.md`).
- [ ] Add scheduled nightly benchmark automation and artifact retention policy.

## P2 - Documentation
- [x] Keep `docs/phase_plan.md` as executive roadmap.
- [x] Keep this file (`docs/TODO.md`) as operational backlog.
- [x] Add `docs/DECISIONS.md` for architecture/parameter decisions with dates and rationale.
- [x] Add `docs/MODEL_REGISTRY.md` with model versions, training windows, and acceptance metrics.

## External-Data / Runtime Blockers
- [x] Historical injury snapshots are unavailable; superseded by usage-weighted roster continuity.
- [x] Historical ownership is unavailable; superseded by the planned popularity/duplication proxy.
- [ ] Add durable checkpoint storage and interrupted-run resume for large candidate generation.

## New Ideas Without Vendor History
- [x] Usage-weighted roster continuity for latent availability (rejected as a standalone captain feature set; retained for role-shock research).
- [ ] Popularity and duplication proxy.
- [ ] Role-shock opportunity reallocation simulations.
- [ ] Online weekly residual learning with shrinkage.
- [ ] Future-safe game-regime ensemble.
- Roadmap: `docs/NEXT_IDEAS.md`.

## Parking Lot
- [ ] Add contest-specific objective functions (cash vs GPP) with separate optimization targets.
- [ ] Add late-swap workflow support for slates with staggered start times.
- [ ] Add weather/news shock scenario simulation for pre-lock stress testing.
