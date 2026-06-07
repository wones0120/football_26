# Matchup Prior Gate Current-Code Comparison

This comparison uses the same first 20 classic DraftKings slates, `1000` candidate lineups per slate, `training_window_slates=24`, `min_training_slates=2`, and `min_training_rows=500`.

| Run | Mean Gap | Lift vs No Matchup |
|---|---:|---:|
| No matchup prior | 133.458 | - |
| Always-on matchup prior `0.15` | 128.762 | 4.696 |
| Gated matchup prior `0.15` | 127.242 | 6.216 |

The gated prior improved by `1.520` points versus always-on in this bounded current-code run.

## Inputs

- No matchup: `docs/optimal_vs_predicted_20slates_no_matchup_current.json`
- Always-on: `docs/optimal_vs_predicted_20slates_matchup_always_on_current.json`
- Gated: `docs/optimal_vs_predicted_20slates_matchup_gate_v1.json`
- Gate model: `docs/matchup_prior_gate_20slates_5000.json`

## Interpretation

The gate is directionally useful but still weak. It should stay experimental until we validate it across more slates and higher candidate counts. The next useful test is a larger 2024-2025 run with enough candidate lineups to reduce random lineup-generation noise.
