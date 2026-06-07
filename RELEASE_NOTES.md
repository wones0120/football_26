# Release Notes

## Unreleased

- Added `scripts/run_matchup_outcome_prior_strength_sweep.py` to evaluate classic matchup-outcome prior strengths against actual-optimal lineup gaps.
- Generated matchup prior sweep reports in `docs/matchup_outcome_prior_strength_sweep_20slates.*`; the current 20-slate run selected `0.15` as the best tested strength.
- Added `scripts/analyze_matchup_prior_help.py` to explain when the matchup prior helps or hurts, with separate future-safe and outcome-only diagnostic buckets.
- Added 5,000-lineup matchup prior validation reports in `docs/matchup_outcome_prior_strength_sweep_20slates_5000.*` and `docs/matchup_prior_help_diagnostics_20slates_5000.*`.
- Exposed matchup outcome model path and prior strength in the classic lineup backtest UI.
- Added `scripts/train_matchup_prior_gate.py` and optional `matchup_prior_gate_model_path` support for classic backtests and ultimate lineup generation.
- Generated `docs/matchup_prior_gate_current_comparison.md`; the current 20-slate run improved mean gap from `133.46` with no matchup prior to `127.24` with the gated prior.
