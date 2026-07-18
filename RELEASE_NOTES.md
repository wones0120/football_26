# Release Notes

## Unreleased

- Converted the main-slate value-driver findings into nine pregame-only features learned by walk-forward classic lineup scoring, covering projected value, high-total exposure, RB spread context, and FLEX construction.
- Added deterministic classic feature-group ablation through `scripts/run_classic_feature_ablation.py`, with paired mean-gap contribution reporting for value-driver and game-environment inputs.
- Added `scripts/run_classic_parameter_sweep.py` with reproducible candidate-count, training-window, and top-target-percentile grids plus compact best-config persistence and source/feature lineage.
- Persisted the initial bounded sweep in `docs/classic_parameter_sweep_12slates.json` and `docs/classic_best_config_12slates.json`; the provisional winner uses 250 candidates, a 4-slate window, and a 95th-percentile target.
- Added point-in-time teammate-availability fields to showdown captain pool/context extraction and an opt-in `--feature-set availability` training mode. The current 41-slate candidate was rejected because historical injury coverage is zero and accuracy regressed, so baseline training and the production artifact remain unchanged.
- Added an injury-free `--feature-set continuity` candidate using prior four-game carries/targets, current salary-pool membership, available-usage concentration, and identity-coverage gating. Honest coverage accounting includes unresolved current salary players; the candidate scored `27.3%` top-1 and `51.5%` top-2 versus the refreshed baseline at `33.3%` and `57.6%`, so it was not promoted.
- Added `docs/NEXT_IDEAS.md` to replace unavailable injury/ownership dependencies with popularity/duplication proxies, role-shock simulations, online residual learning, and future-safe game-regime ensembles.
- Added `scripts/analyze_showdown_captain_drift.py` with sample-gated total-variation alerts across early/mid/late season captain-position priors, plus persisted 2024-2025 JSON and Markdown reports.
- Added salary-relative showdown captain role archetypes and sample-gated, Laplace-smoothed total/spread scenario priors through `scripts/analyze_showdown_captain_scenarios.py`, with persisted 41-slate JSON and Markdown reports.
- Added a no-new-dependency, strict whole-week comparison of rolling baseline, ridge linear, regression-tree, and shallow-neural player projection families; the validation-selected tree achieved `2.610` MAE on the untouched 2025 W12-W18 test window and was not automatically promoted.
- Extended historical simulation backtest rows and UI output with p75 and p95 plus 25-point tail probability, and added a read-only calibration-drift analyzer. The full 15-slate run covered 2,856 players with P75/P90/P95 coverage of `76.4%` / `90.3%` / `94.7%` and no alerts.
- Added explicit classic lineup violation reporting and batch-level hard failures before candidate scoring and final output.
- Added dated architecture decisions and a model registry covering production, experimental, provisional, research, and rejected artifacts.
- Added a dedicated `Analysis & Reports` control-plane area, filtered/collapsed benchmark history, and a safe in-memory ZIP export containing available JSON/Markdown reports and the exact suite config manifest.
- Added `docs/BOOTSTRAP_RUNBOOK.md` with empty-database setup, ingest, identity repair, historical feature/policy build, smoke benchmark, acceptance, and recovery steps.
- Added reproducible percentile-bootstrap confidence intervals and standard errors for classic/showdown gap metrics and captain A/B win-rate/gap-lift metrics, with configurable sample count/confidence level in benchmark CLI/API runs and interval display in new benchmark summaries and the Current Model Card.
- Added selected-slice salary, injury, schedule, and weekly-stat freshness checks through `GET /api/coverage/freshness`, with exact row counts, load ages, explicit thresholds, and `fresh`/`stale`/`missing` badges in the ingestion control plane.
- Added `GET /api/unresolved/triage` and an `Automated Triage by Source / Week / Slate` control-plane report with exact open/recent totals, configurable lookback, grouped source/week/slate counts, and automatic refresh after ingest or resolution actions.
- Added DST-specific identity rules that canonicalize common defense position labels, reuse source/team defense aliases, reject ambiguous team mappings, and prevent defense display-name fallback matching.
- Added pre-write salary and injury CSV validation for required schemas, required identity values, positive integer salaries, and duplicate player identities; failed files preserve the last valid curated slice, report source CSV row numbers, and use deterministic semantic keys when injury IDs are absent.
- Added backend model-default settings and `GET /api/model/defaults` so lineup backtest defaults come from configuration instead of hardcoded UI state.
- Added benchmark control-plane endpoints for run history, suite execution, and safe access to known run artifacts.
- Added benchmark artifact scanning/service helpers plus backend tests covering defaults, run discovery, exact run attribution, and failure artifacts.
- Updated the UI to load backend model defaults, reset lineup benchmark controls to defaults, run the benchmark suite, show recent runs with safe artifact links, and render a Current Model Card from the latest successful run with comparable metrics.
- Added `scripts/run_matchup_outcome_prior_strength_sweep.py` to evaluate classic matchup-outcome prior strengths against actual-optimal lineup gaps.
- Generated matchup prior sweep reports in `docs/matchup_outcome_prior_strength_sweep_20slates.*`; the current 20-slate run selected `0.15` as the best tested strength.
- Added `scripts/analyze_matchup_prior_help.py` to explain when the matchup prior helps or hurts, with separate future-safe and outcome-only diagnostic buckets.
- Added 5,000-lineup matchup prior validation reports in `docs/matchup_outcome_prior_strength_sweep_20slates_5000.*` and `docs/matchup_prior_help_diagnostics_20slates_5000.*`.
- Exposed matchup outcome model path and prior strength in the classic lineup backtest UI.
- Added `scripts/train_matchup_prior_gate.py` and optional `matchup_prior_gate_model_path` support for classic backtests and ultimate lineup generation.
- Generated `docs/matchup_prior_gate_current_comparison.md`; the current 20-slate run improved mean gap from `133.46` with no matchup prior to `127.24` with the gated prior.
