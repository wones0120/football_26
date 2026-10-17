# Training history: 2026 Week 5 diagnostic comparison

Using older training examples helped the neural network substantially on this one observed W5 cohort. The fixed tree changed much less. Recency weighting produced the lowest PPR MAE for both models, but that does not make it the best future training rule: high-PPR errors worsened, position rankings were mixed, and W5 has already been examined repeatedly. Live projections and application defaults remain unchanged.

All 24 fits completed in 61.2s. Six targeted tests passed; 24 saved checkpoints replay every prediction exactly, with canonical row parity and training-only preprocessing checks.

## What was compared

Every arm fits all available labeled games through 2026 W4. The fixed shared residual neural model has 64/32 hidden units, alpha .2, Adam, learning rate .001, 100 epochs; the fixed HGB tree has depth 5, 15 leaves, min leaf 60, L2 10, learning rate .05 and 200 iterations. Both use the same F3 role/PBP features and position encoding, with train-only weighted imputation, scaling and priors. Neither uses W5 for gradients, preprocessing, stopping, budget choice or decay tuning.

These configurations are externally prescribed for this study and informed by prior research that inspected older labels. The 2026-only arm therefore tests restricted training rows; it is not an architecture-selection pipeline that has never seen older outcomes. Fixed budgets retain W4 in all arms and avoid a different final training window.

| Arm | Labeled training rows | Effective weighted rows |
|---|---:|---:|
| 2026_only | 1,342 | 1,342.0 |
| 2025_plus_2026 | 7,034 | 7,034.0 |
| full_equal | 18,259 | 18,259.0 |
| full_recency | 18,259 | 12,741.4 |

Recency weights use calendar-day age since the latest W4 kickoff, a frozen 365-day half-life, and mean-one normalization. They enter MLP partial_fit sample_weight directly and HGB fit sample_weight, plus weighted median/scaler/residual-prior fitting. This is actual weighted loss, not oversampling. Exact weights, row IDs and season/week counts are saved in training_manifest.parquet and training_counts.csv.

## Training examples versus player history

The feature matrix remains identical across arms. Its prior player, team and opponent statistics can cross season boundaries, including 2025 lags for the 2026-only model. A mean-eight-game feature may retain older games even after four current-season games. The study asks which labeled examples to train on while preserving the available pregame information. It does not test discarding every piece of older information. A strict 2026-only feature-history experiment would change the feature information set and remains a separately specified follow-up.

A conservative reference audit confirms older-season base-history references on at least 1,186 of 1,503 positive-snap 2026W1–4 cohort rows and 32 of 256 W5 Sunday Main cohort rows. These are lower bounds, not full older-history prevalence: references can include source rows outside the modeled positive-snap cohort, and the audit does not exhaust expanded mean8/PBP source references. Do not infer that the remaining rows have no older history.

## Assessment coverage

Primary Sunday Main: 256 positive-snap cohort rows, of which 234 have observed labels for all three targets (27 QB, 54 RB, 61 TE, 92 WR). Secondary all-game W5: 352 positive-snap rows, 295 labeled. The 22 primary and 57 secondary missing-label rows are excluded explicitly. Each model/arm predicts exactly the same labeled canonical player-game rows. Observed participation defines the evaluation cohort only; target-game participation never enters a feature. This conditional cohort cannot assess DNP risk or full pre-lock slate coverage.

The initial training positive-snap cohorts are 1,503 / 7,884 / 20,812; missing labels reduce them to the training counts above. Labels are never zero-filled. Training uses all games, not only Sunday Main, identically across arms.

## Primary error on identical rows

| Model | Arm | Targets MAE | Carries MAE | Source PPR MAE |
|---|---|---:|---:|---:|
| tree | 2026_only | 1.5133 | 1.0950 | 5.0293 |
| tree | 2025_plus_2026 | 1.4610 | 1.1185 | 5.0055 |
| tree | full_equal | 1.4493 | 1.0690 | 5.0446 |
| tree | full_recency | 1.4493 | 1.0753 | 4.9681 |
| residual_nn | 2026_only | 1.8560 | 1.3246 | 5.9960 |
| residual_nn | 2025_plus_2026 | 1.6453 | 1.4546 | 5.6235 |
| residual_nn | full_equal | 1.7296 | 1.3105 | 5.1321 |
| residual_nn | full_recency | 1.6439 | 1.1950 | 4.9878 |

Against 2026-only, full recency lowers NN targets MAE 11.4%, carries 9.8% and PPR 16.8%. Tree MAE gains are approximately 4.2%, 1.8% and 1.2%. Full equal weight yields the lowest tree carries MAE (1.0690); tree targets differ by only 0.000014 between full equal and recency. 2025-only addition worsens carries MAE for both models. More history is not uniformly better.

| Model | Arm | Targets RMSE / bias | Carries RMSE / bias | PPR RMSE / bias |
|---|---|---|---|---|
| tree | 2026_only | 2.1924 / +0.0080 | 2.1887 / +0.0467 | 6.5338 / +0.6158 |
| tree | 2025_plus_2026 | 2.1895 / -0.1020 | 2.2540 / -0.0278 | 6.5681 / +0.1751 |
| tree | full_equal | 2.1690 / -0.0583 | 2.1426 / -0.0655 | 6.6446 / +0.1567 |
| tree | full_recency | 2.1590 / -0.0485 | 2.1803 / -0.1038 | 6.5611 / +0.1335 |
| residual_nn | 2026_only | 2.6772 / -0.1740 | 2.3510 / +0.0802 | 8.1562 / +0.6243 |
| residual_nn | 2025_plus_2026 | 2.4619 / -0.1980 | 2.7447 / +0.0786 | 7.6009 / -0.0071 |
| residual_nn | full_equal | 2.4055 / +0.3571 | 2.5557 / +0.3225 | 6.7595 / -0.5968 |
| residual_nn | full_recency | 2.3915 / +0.1758 | 2.3680 / -0.1257 | 6.7906 / -0.6979 |

Bias is prediction minus actual. NN full-recency PPR bias is -0.6979, so its lower average error coexists with underprediction. Tree PPR RMSE is lowest for 2026-only (6.5338), despite full-recency winning MAE (6.5611 RMSE). NN full equal has lower PPR RMSE than full recency (6.7595 versus 6.7906). Ranking and tail quality therefore do not follow a single MAE winner.

## Position and high-workload diagnostics

| Model | Arm | QB PPR MAE | RB PPR MAE | TE PPR MAE | WR PPR MAE | High-PPR MAE |
|---|---|---:|---:|---:|---:|---:|
| tree | 2026_only | 7.7840 | 4.7876 | 4.3881 | 4.7880 | 11.1059 |
| tree | 2025_plus_2026 | 7.7804 | 4.8342 | 4.3983 | 4.6942 | 12.3431 |
| tree | full_equal | 7.9471 | 4.8077 | 4.3870 | 4.7680 | 12.6807 |
| tree | full_recency | 7.5717 | 4.7730 | 4.2917 | 4.7669 | 12.4459 |
| residual_nn | 2026_only | 9.7946 | 5.0668 | 4.6862 | 6.2950 | 12.0466 |
| residual_nn | 2025_plus_2026 | 9.8846 | 5.1188 | 4.4896 | 5.4209 | 12.6196 |
| residual_nn | full_equal | 8.2514 | 5.1708 | 4.6443 | 4.5174 | 12.2188 |
| residual_nn | full_recency | 8.3118 | 4.6163 | 4.2962 | 4.6889 | 13.3813 |

High-workload slices are prespecified realized thresholds, not pregame selectors: 18 rows have targets≥8, nine have carries≥15, and 23 have PPR≥20. In the PPR tail, recency MAE worsens relative to 2026-only for tree (11.1059→12.4459) and NN (12.0466→13.3813). Both weighted models underpredict every high-PPR row. Results.json includes all high-target/carry metrics; the small slices cannot establish reliable tail behavior.

| Model | Arm | Mean position PPR NDCG@5 | Mean position top-five overlap | PPR Spearman |
|---|---|---:|---:|---:|
| tree | 2026_only | 0.7053 | 0.35 | 0.5750 |
| tree | 2025_plus_2026 | 0.6112 | 0.35 | 0.5892 |
| tree | full_equal | 0.6153 | 0.30 | 0.5848 |
| tree | full_recency | 0.6468 | 0.30 | 0.5856 |
| residual_nn | 2026_only | 0.5430 | 0.20 | 0.5086 |
| residual_nn | 2025_plus_2026 | 0.5643 | 0.35 | 0.4912 |
| residual_nn | full_equal | 0.7072 | 0.45 | 0.5253 |
| residual_nn | full_recency | 0.6787 | 0.35 | 0.5453 |

NDCG uses nonnegative source PPR as linear gain, five players per position, and canonical IDs to break ties. Position averages are descriptive. The full-recency tree lowers PPR MAE while its average position NDCG worsens relative to 2026-only; the NN full-equal ranking exceeds full recency. These are point-rank diagnostics, not calibrated upside distributions, contest profit or portfolio evidence.

## Explicit secondary scope

| Model | Arm | All-game targets MAE | Carries MAE | PPR MAE |
|---|---|---:|---:|---:|
| tree | 2026_only | 1.5174 | 1.1217 | 5.0073 |
| tree | 2025_plus_2026 | 1.4793 | 1.1242 | 4.8630 |
| tree | full_equal | 1.4562 | 1.0871 | 4.8951 |
| tree | full_recency | 1.4668 | 1.0984 | 4.8440 |
| residual_nn | 2026_only | 1.8367 | 1.3538 | 5.8858 |
| residual_nn | 2025_plus_2026 | 1.6961 | 1.4196 | 5.7327 |
| residual_nn | full_equal | 1.7017 | 1.2849 | 5.0469 |
| residual_nn | full_recency | 1.6892 | 1.1616 | 4.9393 |

## Saved per-player changes

Predictions.csv/parquet retain canonical identity, game, names for display, actuals, predictions, signed/absolute errors and every arm’s change against the 2026-only model. Names never join records. The following full-recency PPR cases are mechanically selected for each model as largest improvement, largest deterioration, and median absolute error change. They illustrate both directions and are not used to choose a training rule.

| Model | Case | Player / position | Actual | 2026-only prediction | Recency prediction | Change in absolute error |
|---|---|---|---:|---:|---:|---:|
| tree | largest improvement | Tyrod Taylor / QB | -0.20 | 12.01 | 4.35 | -7.66 |
| tree | largest deterioration | Christian Watson / WR | 32.30 | 20.49 | 13.50 | +6.99 |
| tree | median absolute change | Garrett Wilson / WR | 23.40 | 11.31 | 12.23 | -0.92 |
| residual_nn | largest improvement | Michael Wilson / WR | 7.28 | 36.36 | 13.66 | -22.70 |
| residual_nn | largest deterioration | Jacoby Brissett / QB | 25.28 | 23.03 | 10.74 | +12.29 |
| residual_nn | median absolute change | Raheim Sanders / RB | 2.30 | 4.53 | 7.21 | +2.68 |

## Optimization and complexity

All trees complete 200 iterations at actual maximum depth five. Mean leaves per tree range 7.755–14.515; the same minimum leaf count and regularization constrain the smaller window more strongly. NN epoch loss declines in all arms, but this does not prove convergence or exclude optimization artifacts. No stopping validation is reserved and no inference of adequate epochs follows from a declining training curve.

NN 2026-only gets 600 minibatch updates, 2025+2026 gets 2,800 and full history gets 7,200 under the same 100-epoch policy. Larger windows therefore have more optimization steps. Training-only missing indicators also add six input indicators in full-history arms: 10,689 parameters in the first two arms and 11,073 in the full-history arms. Hidden architecture and feature columns are fixed; fitted missing-indicator schema differs because additional old missingness is observed. This is part of the disclosed common preprocessing policy and limits interpreting the comparison as a pure fixed-parameter-capacity intervention. Learning_curves.csv and results.json expose all losses, training MAE, runtimes and actual tree complexity.

Mean-one sample weights make total weight equal row count within each window, avoiding an arbitrary weight scale change between equal and recency runs. Effective weighted full-history sample size is 12,741.4 versus 18,259 equal-weight rows. Batch-level weight sums can differ under shuffling; fixed alpha and normalization do not equate statistical regularization across different training-set sizes.

## Verification and replay

Six tests validate windows, canonical keys, leakage/cutoff guards, recency monotonicity and weight sums, train-only preprocessing, direct weighted MLP gradient changes, and rejection of W5 training. Verify.py checks hashes, exact training row/weight manifests, train-only fitted statistics, canonical assessment parity and every checkpoint against saved full-precision predictions. All 24 checkpoints replay exactly (7,080 prediction rows).

Commands from the repository root:

```sh
PYTHONPATH=. .venv/bin/python -m pytest research/training_history_comparison_20261013/test_study.py -q
PYTHONPATH=. .venv/bin/python research/training_history_comparison_20261013/verify.py
PYTHONPATH=. .venv/bin/python research/training_history_comparison_20261013/report.py
```

The trainer refuses to overwrite its freeze. The direct-entry-point trainer serialized HistoryModel/WeightedPreprocess under __main__; verify.py restores those exact class names before joblib loading without changing checkpoint bytes. For manual loading, import study and assign these classes to __main__ first, or use verify.py as the replay entry point. An initial replay check also assumed partial_fit n_iter_ accumulated epochs; sklearn records the current partial-fit call there, so verification correctly checks the 100-entry loss_curve_ instead. Neither fix changes models or results.

## Limits and next step

This is retrospective revised-data development. Existing W5 outcomes and earlier seasons informed prior research. Source IDs and period/completion guards preserve available historical ordering, but rebuilt/revised sources lack original predecision receipt evidence; stored cutoffs are not proof of actual availability. Features do not use W5 outcomes or target-game participation, but evaluation membership is conditioned on observed participation. No W6+ outcomes were loaded. Source PPR differs from DraftKings scoring.

Do not promote a model from one repeatedly inspected week. Preserve all four arms and repeat their exact specifications on genuinely predecision archived future forecasts; freeze source receipts, cohort and scoring before lock, then report every target and tail/rank diagnostic at each week. Weight decay and epoch budgets stay frozen through that comparison. A separately frozen strict-2026-history sensitivity or matched-optimization-budget study may explain mechanisms, but neither should be mined from W5.

Artifacts: SPECIFICATION.md (design), freeze.json (hashes/configs/versions), training_manifest.parquet and training_counts.csv (windows/weights), assessment_manifest.csv (coverage), models/ (24 checkpoints), predictions.csv/parquet (all player changes), metrics.csv/results.json (all primary/secondary metrics), learning_curves.csv, verification.json, training_log.txt. Only this study directory was written.
