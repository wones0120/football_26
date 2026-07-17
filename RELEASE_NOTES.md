# Release Notes

## Unreleased

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
