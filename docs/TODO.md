# Football_26 TODO Backlog

Last updated: 2026-07-17

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
- [ ] Add data freshness checks for salaries/injuries/schedules/stats with UI status badges.

## P0 - Evaluation Framework
- [x] Create a canonical benchmark command that runs:
  - classic optimal-vs-predicted
  - showdown baseline
  - showdown captain-informed
  - main-slate value-driver refresh
- [x] Save benchmark outputs under dated folders and compare against previous run with delta tables.
- [ ] Add confidence intervals / bootstrap error bars for gap metrics and win-rate metrics.

## P1 - Main Slate Modeling (Classic)
- [ ] Convert main-slate value-driver findings into learned features used by lineup scoring.
- [ ] Add game-environment features for classic lineups:
  - team implied totals
  - game totals
  - spread context
  - opponent-adjusted matchup features
- [ ] Add ablation tests for classic lineup scoring to measure feature contribution.
- [ ] Add classic parameter sweep (candidate lineups per slate, training windows, thresholds) and persist best config.

## P1 - Showdown Modeling
- [ ] Add teammate-availability context to captain archetype model (who was active/usage context).
- [ ] Add season-segment drift checks and automatic alerts when captain priors shift materially.
- [ ] Extend captain modeling beyond position class (role/archetype buckets within position).
- [ ] Add showdown scenario analysis module:
  - which captain archetypes win by matchup/game context
  - descriptive and predictive views for future slates

## P1 - Player Projection Engine
- [ ] Implement opponent-specific player scoring distributions (not just global history).
- [ ] Add teammate-on/off context features (availability and usage interactions).
- [ ] Train and compare model families (baseline linear/tree vs neural net) under strict time-split validation.
- [ ] Calibrate uncertainty (mean, p75, p90, tail risk) and track calibration drift.

## P1 - Lineup Generator and Policy Learning
- [ ] Build policy-learning loop from historical actual top lineups (top-k per slate) into lineup scoring.
- [ ] Add richer constraints and learned exposures:
  - ownership-aware leverage
  - salary structure priors
  - correlation and anti-correlation controls
- [ ] Add robust validity checks for every generated lineup with hard fail logs for violations.
- [ ] Support 100k+ candidate experiments with deterministic seeds and resumable runs.

## P2 - UI / Control Plane
- [ ] Add dedicated "Analysis" area for generated reports (showdown, main slate, combined).
- [ ] Add run history explorer with filters (source, season range, slate type, model config).
- [ ] Add expandable/collapsible sections for all heavy tables by default.
- [ ] Add export bundle action (JSON + MD report + config snapshot).

## P2 - Ops / Engineering
- [ ] Add integration tests for ingestion->curation->backtest critical path.
- [ ] Add migration smoke test and schema drift checker in CI.
- [ ] Add runbook for full environment bootstrap from empty database.
- [ ] Add scheduled nightly benchmark automation and artifact retention policy.

## P2 - Documentation
- [ ] Keep `docs/phase_plan.md` as executive roadmap.
- [ ] Keep this file (`docs/TODO.md`) as operational backlog.
- [ ] Add `docs/DECISIONS.md` for architecture/parameter decisions with dates and rationale.
- [ ] Add `docs/MODEL_REGISTRY.md` with model versions, training windows, and acceptance metrics.

## Parking Lot
- [ ] Add contest-specific objective functions (cash vs GPP) with separate optimization targets.
- [ ] Add late-swap workflow support for slates with staggered start times.
- [ ] Add weather/news shock scenario simulation for pre-lock stress testing.
