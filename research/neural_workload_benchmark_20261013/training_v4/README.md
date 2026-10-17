# Neural training V4: useful progress, still retrospective

**Better training substantially improved the neural control.** Across twelve normal-week Sunday Main blocks, residual-to-history and position-aware workload models reduced full-feature errors versus the prior shared MSE neural model. The strong tree still had the lowest pooled target/carry/PPR errors. The result supports these training changes as candidates for a prospective comparison; it does not establish neural superiority.

## What changed

- Residual neural model: learn corrections to recent-three history, train-scale residuals, preserve Adam state across epochs, and select checkpoints on later whole-week stopping data.
- Position model: shared learning across players within QB/RB/WR/TE; separately predict observed-positive probability and positive log-count amount for workloads, with training-only smearing. PPR uses position-specific residual heads. Sparse/single-class cases have explicit train-only fallbacks.
- Temporal training: two fixed settings per method, three chronological rolling folds, separate stopping/selection/calibration blocks. Selection uses equal-position normalized MAE rather than pooled error alone.
- Uncertainty: separate calibration weeks supply empirical residual 90% intervals; evaluate subsequent coverage/width/misses. They are not learned ceilings or joint/count distributions.

Both F2 (50) and F3 (68) inputs from V3 remain unchanged. Prior MSE NN and HistGradientBoosting controls receive the same labeled rows, feature family, fit periods and two configuration choices. New models use no player identity features, new current-week news, target-week realized snaps, or future games. Labels remain conditional on observed positive offensive participation; missing stats/DNP stay distinct from observed zeros.

## Evidence and chronology

Prior 2024–2025 model/slate reports cover broad historical blocks. We cannot prove an untouched historical holdout. All rolling results are revised-data retrospective development, and 2026 Weeks 4–5 are explicitly already-inspected diagnostics. Freezing V4 does not restore outcome blindness. outcome_inspection_audit.json documents the evidence; PROSPECTIVE_PROTOCOL.md reserves 2026 Weeks 6–9 and requires predecision saved forecasts, original source/model hashes and a pregame candidate universe. No future result or automatic monitoring was loaded/created.

Fold A: fit through 2024W4; stopW5–6; selectW7; calibrateW8; assessW9–12. Fold B uses the equivalent 2025W4 boundary and assesses 2025W9–12. Fold C fits through 2025W8, stopsW9–10, selectsW11, calibratesW12 and assessesW13–16. Earlier assessment rows can be training in later folds; these are chronological forecasts, not independent randomized experiments. No diagnostic block enters its own fitting/stopping/selection/calibration.

There are 2,756 observed labels across 131 Sunday Main games in 12 normal weeks. 3,094 positive-snap participants were identified; unobserved stat labels remain missing. V3 native-ID/canonical/game-time safeguards and immutable revised sources are reused, including their missingness/alias limitations.

## Rolling pooled MAE (lower is better)

| Inputs | Method | Targets | Carries | Source PPR |
|---|---|---:|---:|---:|
| F2_efficiency | tree | 1.431 | 1.216 | 4.632 |
| F2_efficiency | prior_nn | 1.507 | 1.329 | 4.793 |
| F2_efficiency | residual_nn | 1.433 | 1.223 | 4.734 |
| F2_efficiency | position_nn | 1.445 | 1.282 | 4.786 |
| F3_role_pbp | tree | 1.412 | 1.213 | 4.576 |
| F3_role_pbp | prior_nn | 1.513 | 1.395 | 4.913 |
| F3_role_pbp | residual_nn | 1.419 | 1.277 | 4.660 |
| F3_role_pbp | position_nn | 1.422 | 1.250 | 4.821 |

For full 68 inputs, prior NN→residual NN gives targets 1.513→1.419 and PPR 4.913→4.660; position NN gives carries 1.395→1.250. These are approximately 6%, 5% and 10% gains against the same-window neural control. The full tree remains at 1.412/1.214/4.576. F2 residual carries are 1.223 versus the paired tree 1.216. Keep all methods/families visible; selecting only the best error column would exaggerate progress.

## Position workload and high-workload checks

| Position | n | Full tree targets MAE | Residual targets MAE | Position targets MAE | Full tree carries MAE | Residual carries MAE | Position carries MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| QB | 321 | 0.080 | 0.151 | 0.031 | 1.719 | 1.920 | 1.824 |
| RB | 670 | 1.315 | 1.298 | 1.357 | 3.623 | 3.582 | 3.717 |
| WR | 1139 | 1.817 | 1.809 | 1.812 | 0.231 | 0.310 | 0.234 |
| TE | 626 | 1.463 | 1.490 | 1.497 | 0.164 | 0.239 | 0.165 |

| High workload subgroup | n | Full tree MAE | Prior NN MAE | Residual NN MAE | Position NN MAE |
|---|---:|---:|---:|---:|---:|
| targets | 493 | 2.669 | 2.857 | 2.642 | 2.778 |
| carries | 274 | 4.565 | 5.053 | 4.503 | 4.677 |
| fantasy_points_ppr | 499 | 8.664 | 8.768 | 8.689 | 9.204 |

Zero/positive, sparse-history, prior-team changes and workload-shift groups remain in the full fold results. Passing and carry targets have very different position distributions; better handling of observed zeros is useful, but a DNP/availability probability is still missing. No user preferences or eligibility changes enter this research.

## Learning curves: what the training actually did

All 288 newly trained curve-bearing heads stopped before 300 epochs; median best checkpoint was 18. None reached the cap. In 5 heads, stopping error deteriorated by >10% while training fit continued improving after the best checkpoint. Most other heads plateaued. This supports temporal stopping/residual anchoring; it does not prove every capacity or architecture is adequate or that more epochs can never help.

learning_curves.csv retains every epoch, fit/config/head, training loss/metric, stopping metric and best checkpoint. Classifier curves compare training/stopping Brier; positive-count heads use standardized-log RMSE. Residual heads have scaled training RMSE and actual-target stopping MAE (different units); do not plot them as if they share one scale. Each fitted metadata record also retains comparable actual train/stopping MAE. Prior NN loss curves and stopping-block errors are preserved as controls.

## Ranking and combinations

| Full-feature method | QB NDCG | RB NDCG | WR NDCG | TE NDCG | Pair top10 realized overlap |
|---|---:|---:|---:|---:|---:|
| tree | 0.586 | 0.677 | 0.615 | 0.640 | 23.3% |
| prior_nn | 0.542 | 0.658 | 0.589 | 0.650 | 19.2% |
| residual_nn | 0.650 | 0.662 | 0.596 | 0.662 | 23.3% |
| position_nn | 0.573 | 0.608 | 0.636 | 0.610 | 18.3% |

These are the same predeclared V3 point-ranking diagnostics: topK QB3/RB8/WR10/TE5, actual PPR boom thresholds 25/20/20/15, conditional same-team QB+WR/TE pair-sum top10. Improved average error is not automatically breakout capture or portfolio value. Pair sums have no learned correlation, salaries, ownership or roster constraints; shared-player pairs are not independent. They do not validate correlated lineup outcomes or profitability.

## Empirical uncertainty

| Full-feature method | Targets coverage | Carries coverage | PPR coverage | PPR mean interval width |
|---|---:|---:|---:|---:|
| tree | 92.6% | 92.6% | 91.4% | 21.44 |
| prior_nn | 92.9% | 92.8% | 92.1% | 24.44 |
| residual_nn | 92.1% | 92.5% | 91.7% | 21.98 |
| position_nn | 92.7% | 91.3% | 90.8% | 21.78 |

Nominal 90% intervals have roughly 91–93% pooled rolling coverage, but position-specific coverage/drift/small calibration groups still matter. Position radius needs 30 calibration rows; otherwise it falls back pooled. One calibration week is limited. Temporal dependence and revised historical evidence prevent a guarantee of forward/conditional calibration. Upper interval bounds are residual ranges, not trained ceilings; constant per-position radius adds no distinct within-position tail ranking. Workload positive-probability Brier/reliability bins are saved in diagnostic_results.json and the supplemental rolling_positive_probability_audit.json. The supplemental audit replays only already-selected hurdle fits, verifies original point predictions/MAE, and does not retune or change the frozen results.

## Already-inspected2026 W4/W5 diagnostics

All methods were retrained on the same rows through 2026W2. W3 is calibration only. New NN epoch counts use historical stopping medians; final fixed-epoch diagnostic curves use training-tail data solely for reporting, not adaptation. This window differs from V3’s train-throughW3, so compare the retrained controls here rather than treating cross-version errors as a controlled change. There are 485 observed Sunday labels across 23 games.

| Inputs | Method | Targets MAE | Carries MAE | PPR MAE |
|---|---|---:|---:|---:|---:|
| F2_efficiency | tree | 1.523 | 1.149 | 4.782 |
| F2_efficiency | prior_nn | 1.558 | 1.167 | 4.920 |
| F2_efficiency | residual_nn | 1.538 | 1.091 | 4.791 |
| F2_efficiency | position_nn | 1.501 | 1.087 | 4.854 |
| F3_role_pbp | tree | 1.497 | 1.096 | 4.821 |
| F3_role_pbp | prior_nn | 1.610 | 1.306 | 4.952 |
| F3_role_pbp | residual_nn | 1.553 | 1.183 | 4.853 |
| F3_role_pbp | position_nn | 1.542 | 1.097 | 5.038 |

These diagnostics are mixed: F2 position workload errors improve versus its paired tree here, while full-feature position PPR is worse than the prior NN. None is new independent evidence. Every method’s player predictions/intervals are retained; no model winner or live default was promoted.

## Next useful step

Treat residual-to-history with temporal stopping as a stronger neural control. Keep the position/observed-zero workload branch as a candidate rather than forcing it into PPR. The tree remains a strong comparator. Measure prospective normal-week stability and tail/role changes with predecision receipts before considering production use. A future unconditional projection needs availability/participation forecasts; correlated lineup intelligence needs shared-game uncertainty, not point-pair ranking.

## Reproduction, artifacts and runtime

Rolling training used 144 predefined configuration fits and took 227.42s on one CPU thread; 24 final model fits/ensembles took 51.14s. Neural head cap 120s, epoch cap 300, two settings per method. Six new targeted tests pass; all25 V1–V4 tests pass (six old synthetic convergence warnings). Two real prior-NN rolling control fits also reached their300-iteration budget; their warnings are retained. New temporally stopped heads and final diagnostic fits did not warn. Existing studies/sources and all application behavior remain intact.

```sh
PYTHONPATH=. .venv/bin/python -m pytest research/neural_workload_benchmark_20261013/training_v4/test_training.py -q
.venv/bin/python research/neural_workload_benchmark_20261013/training_v4/runner.py --rolling
.venv/bin/python research/neural_workload_benchmark_20261013/training_v4/runner.py --diagnostics
.venv/bin/python research/neural_workload_benchmark_20261013/training_v4/probability_audit.py
.venv/bin/python research/neural_workload_benchmark_20261013/training_v4/verify.py
.venv/bin/python research/neural_workload_benchmark_20261013/training_v4/report.py
```

The existing frozen rolling file must be preserved. Repeat diagnostic fitting with --diagnostics; to rerun the complete rolling phase, copy code/spec into a new versioned directory or use a separately identified output location. The current rolling command refuses to overwrite its frozen result at completion. Fitted final weights/checkpoints and train-only preprocessors are in fitted_models/*.joblib. Import this directory’s models module before loading custom-class artifacts. verify.py reloads all24 saved models and exactly recomputes their errors, without fitting or needing a new snapshot. Code/library/spec/matrix/model hashes and all candidate selection/epoch records are retained. Historical checkpoint curves and scores are persisted; historical weights can be reproduced by the exact frozen training command. No dependency install or ingestion/app/default change was made.
