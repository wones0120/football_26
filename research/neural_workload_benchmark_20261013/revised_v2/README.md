# Historical neural/tree workload comparison — revised-data V2

**We ran the comparison. The small neural model did not show a consistent advantage.** Its basic target MAE was slightly better than the tree, but carries and PPR favored the tree. Adding the richer common features worsened both neural workload errors. No model/default was promoted.

The source archive is revised historical data imported after the games. The user approved this separate retrospective study; V1’s contemporaneous-availability feasibility audit remains unchanged. Same/future-game outcomes are excluded from inputs and whole-week splits are enforced. This is not a replay of actual past app predictions or a pristine held-out claim.

## Week and sample

2025 Week 18 was chosen before prediction scoring because it is the most recent complete prior-season regular-season week with at least 200 recorded skill-player rows. Training: 2023–2024 and 2025 Weeks 1–12 (48 week blocks, 15,618 rows). Validation: 2025 Weeks 13–17 (5 blocks, 1,734 rows). Test: 2025 Week 18 (1 block, 350 rows). No tuning on validation or test. All models use the same measured target samples and input treatment.

The population is QB/RB/WR/TE with an observed weekly stat record, conditional on being recorded. It is not a verified active-roster or positive-offensive-snap population. Absent rows and DNP are never invented as zero labels; present numeric zeros remain zero. Each label has 350 observed test rows. Historical alias joins use native source IDs and unique canonical player IDs; no names join data. Player/team IDs are excluded as predictors. Current-game team membership is used only in outcomes/diagnostics; prior team context follows the last recorded player team. Matchup/opponent metadata is reconstructed from the historical source, without original pregame evidence.

## Test MAE (lower is better)

| Model / shared features | Targets | Carries | Source PPR |
|---|---:|---:|---:|
| Recent-three history | 1.409 | 1.404 | 4.461 |
| Tree, basic | 1.408 | 1.352 | 4.365 |
| Neural, basic | 1.380 | 1.357 | 4.436 |
| Tree, enriched | 1.402 | 1.401 | 4.346 |
| Neural, enriched | 1.432 | 1.463 | 4.467 |

Targets and carries are the main tasks. PPR is an auxiliary source-defined full-PPR label, **not DraftKings scoring** and not the production app’s final fantasy prediction. The research tree is sklearn HistGradientBoosting with a fixed small configuration; production uses GradientBoosting plus calibration, role/opportunity, market and availability handling. This study does not compare against captured production predictions.

## Test RMSE

| Model / shared features | Targets | Carries | Source PPR |
|---|---:|---:|---:|
| Recent-three history | 2.158 | 3.170 | 6.558 |
| Tree, basic | 2.032 | 2.896 | 5.981 |
| Neural, basic | 2.010 | 2.924 | 6.155 |
| Tree, enriched | 2.009 | 2.958 | 5.969 |
| Neural, enriched | 2.054 | 2.947 | 6.132 |

## Enriched test errors by position

| Position | n | Tree targets MAE | Neural targets MAE | Tree carries MAE | Neural carries MAE | Tree PPR MAE | Neural PPR MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| QB | 43 | 0.077 | 0.104 | 1.735 | 1.935 | 6.208 | 6.241 |
| RB | 92 | 1.256 | 1.270 | 4.002 | 4.011 | 4.425 | 4.530 |
| WR | 140 | 1.954 | 2.030 | 0.246 | 0.306 | 4.167 | 4.168 |
| TE | 75 | 1.311 | 1.274 | 0.175 | 0.229 | 3.517 | 3.930 |

## Concrete player predictions

Illustrations are selected deterministically by prior targets+carries within position: two RB, two WR, one TE, one QB. Selection does not use Week 18 outcomes. Values below use the enriched common matrix. All 350 players and all five predictions per target are in `player_predictions_2025w18.csv`.

| Player | Pos | Actual targets | Tree | Neural | Actual carries | Tree | Neural | Actual PPR | Tree | Neural |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Bijan Robinson | RB | 3.00 | 7.44 | 6.97 | 15.00 | 16.40 | 20.03 | 7.30 | 21.14 | 23.05 |
| Christian McCaffrey | RB | 7.00 | 4.21 | 5.02 | 8.00 | 17.03 | 18.24 | 11.70 | 18.68 | 18.63 |
| Amon-Ra St. Brown | WR | 15.00 | 8.66 | 7.69 | 0.00 | 0.12 | 0.50 | 24.90 | 16.48 | 14.74 |
| Puka Nacua | WR | 11.00 | 9.00 | 9.75 | 2.00 | 0.20 | 0.44 | 26.00 | 17.71 | 21.42 |
| Trey McBride | TE | 8.00 | 8.47 | 7.18 | 0.00 | 0.11 | 0.87 | 13.50 | 14.81 | 13.98 |
| Bo Nix | QB | 0.00 | 0.08 | 0.00 | 8.00 | 5.45 | 5.03 | 10.54 | 19.24 | 19.14 |

## Have we used the full breadth of data?

**No.** The production model explicitly fits salary/home/markets, player and positional-defense history, lagged missing-share measures, snap share, offensive-role importance/completeness and position. Targets/carries/team shares also feed role calculations and opportunity postprocessing rather than appearing directly in its fitted feature list. Explicit pregame availability, depth/workload, market refresh and calibration affect final projections. Having these hooks does not prove every field has populated historical coverage.

Both research models started with the same 14 numeric features plus position: prior-three and last targets/carries/PPR, workload trends and shares, prior team workload, history count and gap. We then added the same 19 numeric fields to both: ten lagged passing/rushing/receiving stats, four efficiency ratios, two team passing-volume proxies, and three prior opponent positional outcome measures. The shared source adapters are now implemented and hashed. Each model receives identical features within each treatment.

Snaps/routes, verified participation, historical injury/depth/news, historical salary/markets/home and situational play-by-play/red-zone families are not in this packet. They are excluded rather than guessed. Lagged raw stats are available, but contemporary versions are not proven. The pass fraction is a partial skill-player attempts/(attempts+carries) proxy, not neutral pass rate or PROE. The opponent allowed quantities condition on recorded skill-player rows. Availability flags come from train-fitted missing indicators; feature-level coverage is saved in the manifest. Further available raw EPA/CPOE, air-yard, first-down, yards-after-catch and fumble measures remain outside the fixed feature set; their observed source coverage is listed in the breadth audit for future experiments.

## Diagnostics and interpretation

- targets: enriched tree/neural bias 0.033/-0.002; +20% prior usage mean response 0.231/0.315; partial team aggregate MAE 6.891/7.032.
- carries: enriched tree/neural bias -0.181/-0.055; +20% prior usage mean response 0.208/0.226; partial team aggregate MAE 7.444/7.397.
- fantasy_points_ppr: enriched tree/neural bias 0.658/0.346; +20% prior usage mean response 0.378/0.572; partial team aggregate MAE 21.014/22.024.

Team sums cover only the conditional recorded skill-player population, not full team pass/rush budgets. No redistribution is enforced. +20% sensitivity scales prior usage and associated shares/trends, adjusts denominator-based efficiency ratios, and flags any resulting shares above one; it does not model a coherent injury substitution. Residual quantiles and errors are diagnostics, not calibrated intervals or joint simulation uncertainty.

Validation/test metrics also retain sparse-history, observed-zero, high-opportunity, team-change and workload-shift groups. Groups below 30 rows are explicitly descriptive. The predefined >=5% NN MAE gain against both history and its paired tree for both workload tasks was **not met**. One Week 18 test has unusual resting/role-change dynamics and cannot establish season-wide superiority. Enrichment is not automatically useful; further data work should prioritize reliable participation/snaps and historical role/context, then additional frozen weeks to measure stability.

Historical workload research can inform player-level volume expectations, then football scoring/uncertainty and role/availability handling can translate them to fantasy projections. This benchmark adds neither live workload forecasts nor LLM fantasy adjustments to the app. No profitability claim.

## Runtime, validation and reproduction

Data preparation took 10.48 seconds; all twelve bounded real model fits and evaluation took 11.89 seconds on one CPU thread. The MLP is (16,8), fixed seed and iteration cap. Two real enriched fits warned that the fixed 150-iteration cap was reached; warnings and actual iteration counts are retained and no outcome-driven retry occurred. Six V2 tests passed; tests cover lagging, no same-week source influence, missing/zero handling, byes/transfer context, identity/team codes, splits, matrix parity and deterministic training-only preprocessing. Original V1’s seven tests also remain available.

```sh
.venv/bin/python research/neural_workload_benchmark_20261013/revised_v2/experiment.py --prepare
.venv/bin/python research/neural_workload_benchmark_20261013/revised_v2/experiment.py --run
.venv/bin/python research/neural_workload_benchmark_20261013/revised_v2/breadth_audit.py
.venv/bin/python research/neural_workload_benchmark_20261013/revised_v2/report.py
PYTHONPATH=. .venv/bin/python -m pytest research/neural_workload_benchmark_20261013/revised_v2/test_experiment.py -q
```

All writes stay in this V2 research directory. Sources, matrix, labels, specification, code and production source-inspection hashes are recorded. Predictions are deterministic to the saved runtime/library versions. Existing artifacts, app/config/database state and defaults are untouched.

A complete repeated benchmark took 11.89 seconds (first run 12.57); all player prediction bytes and every metric matched exactly. See `repeatability.json`.
