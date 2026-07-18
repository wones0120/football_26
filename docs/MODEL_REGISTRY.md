# Model Registry

Last reviewed: 2026-07-18

| Model / Policy | Version / Artifact | Training or analysis window | Acceptance evidence | Status |
|---|---|---|---|---|
| Showdown captain archetype | `docs/showdown_captain_model_2024_2025.json` | DraftKings 2024-2025; 41 slates, 33 evaluated | Top-1 `36.4%`, top-2 `60.6%`; baseline top-1 `24.2%` | Production input |
| Showdown captain prior strength | `docs/showdown_captain_strength_sweep_2024_2025_2500.json` | 39 paired slates; 2,500 candidates/slate | Strength `0.35`; mean-gap lift `+6.741`, win rate `61.5%` | Production default |
| Showdown availability candidate | Opt-in `--feature-set availability`; no production artifact | 41 slates; zero injury-report coverage | `30.3%` top-1 / `51.5%` top-2, below current-code baseline | Rejected pending data |
| Showdown usage-continuity candidate | `docs/showdown_captain_continuity_model_2024_2025.json` | 2024-2025; prior four-game carries/targets; 41 slates, 33 evaluated | `27.3%` top-1 / `51.5%` top-2 versus refreshed baseline `33.3%` / `57.6%` | Rejected standalone; retained for role-shock research |
| Showdown role/scenario priors | `docs/showdown_captain_scenarios_2024_2025.json` | 2024-2025; 41 slates | 11 role archetypes; seven total/spread cells; five-slate fallback gate | Research |
| Classic value-driver prior | `docs/main_slate_value_driver_analysis_2024_2025.json` | DraftKings 2024-2025; 27 main slates | Nine learned pregame value/construction features | Production input |
| Classic lineup parameter sweep | `docs/classic_best_config_12slates.json` | 12 chronological slates | 10/12 completed; mean gap `134.428`; median `131.110` | Provisional |
| Matchup outcome intelligence | `docs/matchup_outcome_intelligence_2024_2025.json` | DraftKings 2024-2025 | `0.15` prior improved mean gap by `4.65` at 5,000 candidates | Experimental default |
| Matchup prior gate | `docs/matchup_prior_gate_20slates_5000.json` | 18 paired slates | Future-safe rule gate; broader validation still required | Experimental |
| Player matchup ridge blend | Built point-in-time from `player_game_feature_matrix` | All rows before target week, position-specific | Enabled only when validation MAE improves by more than `0.5%`; blend weight scales with lift | Production |
| Projection family comparison | `docs/projection_model_family_comparison_2024_2025.json` | Train through 2025 W07; validate W08-W11; test W12-W18 | Tree test MAE `2.610`, ridge `3.044`, neural `2.901` | Research; not promoted |
| Simulation uncertainty calibration | `docs/projection_calibration_drift_2024_2025.json` | 15 Sunday-main slates; 2,856 players | P75/P90/P95 `76.4%` / `90.3%` / `94.7%`; tail error `+0.2` points; zero alerts | Accepted |
| Historical top-lineup policy | `actual_top_lineup*` tables and `run_actual_top_lineup_learning` | Strictly prior slates within configured window | Top-k labels, walk-forward selection uplift, feature insights | Production-capable |

## Registry Rules

1. Production promotion requires time-safe validation and a persisted artifact or deterministic training definition.
2. Research artifacts never replace product defaults automatically.
3. Every artifact must record its source, season/week window, feature set or hash where available, random seed, and acceptance metric.
4. Rejected models remain documented so weak candidates are not unknowingly repeated.
