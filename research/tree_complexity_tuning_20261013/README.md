# Tree depth and complexity tuning

Tuning produced the following frozen comparisons. Added complexity and stopping did not create a uniform improvement across tasks and feature sets.

targets F2_efficiency: 1.4308 → 1.4293 MAE (-0.10%), 7/12 weeks improved.
targets F3_role_pbp: 1.4121 → 1.4097 MAE (-0.17%), 6/12 weeks improved.
carries F2_efficiency: 1.2157 → 1.2066 MAE (-0.75%), 7/12 weeks improved.
carries F3_role_pbp: 1.2135 → 1.2062 MAE (-0.60%), 9/12 weeks improved.
fantasy_points_ppr F2_efficiency: 4.6324 → 4.6654 MAE (+0.71%), 3/12 weeks improved.
fantasy_points_ppr F3_role_pbp: 4.5759 → 4.5750 MAE (-0.02%), 4/12 weeks improved.

Completed 180 fits in 656.8s. No live projections, defaults, production models, database records or upstream research artifacts were changed. Research HistGradientBoosting differs from the production pipeline.

All results are retrospective revised-data development on previously inspected historical outcomes. Assessment is 12 Sunday Main week blocks, 2,756 labeled positive-snap participants per target (conditional on observed participation). Source PPR is not DraftKings scoring. No W6+ outcomes were read.

## Pooled error

| Target | Features | Method | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|
| carries | F2_efficiency | old_tree | 1.2157 | 2.5151 | +0.0338 |
| carries | F2_efficiency | position_nn | 1.2822 | 2.7137 | +0.0567 |
| carries | F2_efficiency | prior_nn | 1.3290 | 2.7715 | -0.0429 |
| carries | F2_efficiency | residual_nn | 1.2233 | 2.6915 | -0.2353 |
| carries | F2_efficiency | tuned_tree | 1.2066 | 2.5014 | +0.0377 |
| carries | F3_role_pbp | old_tree | 1.2135 | 2.4987 | +0.0295 |
| carries | F3_role_pbp | position_nn | 1.2502 | 2.6059 | +0.1041 |
| carries | F3_role_pbp | prior_nn | 1.3950 | 2.8233 | +0.1768 |
| carries | F3_role_pbp | residual_nn | 1.2771 | 2.5169 | +0.0689 |
| carries | F3_role_pbp | tuned_tree | 1.2062 | 2.4840 | +0.0357 |
| fantasy_points_ppr | F2_efficiency | old_tree | 4.6324 | 6.2802 | +0.2222 |
| fantasy_points_ppr | F2_efficiency | position_nn | 4.7857 | 6.5166 | +0.2091 |
| fantasy_points_ppr | F2_efficiency | prior_nn | 4.7927 | 6.6399 | +0.0909 |
| fantasy_points_ppr | F2_efficiency | residual_nn | 4.7343 | 6.4225 | +0.2497 |
| fantasy_points_ppr | F2_efficiency | tuned_tree | 4.6654 | 6.3225 | +0.2337 |
| fantasy_points_ppr | F3_role_pbp | old_tree | 4.5759 | 6.2213 | +0.2895 |
| fantasy_points_ppr | F3_role_pbp | position_nn | 4.8208 | 6.5333 | +0.1610 |
| fantasy_points_ppr | F3_role_pbp | prior_nn | 4.9134 | 6.7061 | +0.3731 |
| fantasy_points_ppr | F3_role_pbp | residual_nn | 4.6604 | 6.3317 | +0.2747 |
| fantasy_points_ppr | F3_role_pbp | tuned_tree | 4.5750 | 6.2188 | +0.2220 |
| targets | F2_efficiency | old_tree | 1.4308 | 2.0164 | +0.1019 |
| targets | F2_efficiency | position_nn | 1.4451 | 2.0707 | +0.0978 |
| targets | F2_efficiency | prior_nn | 1.5074 | 2.1511 | -0.0635 |
| targets | F2_efficiency | residual_nn | 1.4328 | 2.0117 | +0.0877 |
| targets | F2_efficiency | tuned_tree | 1.4293 | 2.0086 | +0.1135 |
| targets | F3_role_pbp | old_tree | 1.4121 | 1.9798 | +0.1136 |
| targets | F3_role_pbp | position_nn | 1.4223 | 2.0253 | +0.0701 |
| targets | F3_role_pbp | prior_nn | 1.5130 | 2.1382 | +0.0514 |
| targets | F3_role_pbp | residual_nn | 1.4192 | 2.0005 | +0.0761 |
| targets | F3_role_pbp | tuned_tree | 1.4097 | 1.9954 | +0.1002 |

## Tuned tree minus unchanged tree

| Target | Features | MAE difference | Whole-week bootstrap 95% | Improved weeks |
|---|---|---:|---|---:|
| targets | F2_efficiency | -0.0015 | [-0.0120, +0.0090] | 7/12 |
| targets | F3_role_pbp | -0.0025 | [-0.0136, +0.0096] | 6/12 |
| carries | F2_efficiency | -0.0091 | [-0.0254, +0.0083] | 7/12 |
| carries | F3_role_pbp | -0.0073 | [-0.0183, +0.0047] | 9/12 |
| fantasy_points_ppr | F2_efficiency | +0.0330 | [-0.0039, +0.0787] | 3/12 |
| fantasy_points_ppr | F3_role_pbp | -0.0009 | [-0.0403, +0.0303] | 4/12 |

## Selected complexity

| Fold / target / feature / method | Configuration | Iterations | Max actual depth | Mean leaves |
|---|---|---:|---:|---:|
| A_2024/targets/F2_efficiency/old_tree | 1 | 200 | 21 | 31.0 |
| A_2024/targets/F2_efficiency/tuned_tree | slow_shallow | 325 | 3 | 6.7 |
| A_2024/targets/F3_role_pbp/old_tree | 0 | 150 | 12 | 15.0 |
| A_2024/targets/F3_role_pbp/tuned_tree | regularized | 325 | 5 | 12.8 |
| A_2024/carries/F2_efficiency/old_tree | 1 | 200 | 21 | 31.0 |
| A_2024/carries/F2_efficiency/tuned_tree | shallow | 300 | 3 | 6.9 |
| A_2024/carries/F3_role_pbp/old_tree | 1 | 200 | 20 | 31.0 |
| A_2024/carries/F3_role_pbp/tuned_tree | shallow | 325 | 3 | 6.9 |
| A_2024/fantasy_points_ppr/F2_efficiency/old_tree | 1 | 200 | 20 | 31.0 |
| A_2024/fantasy_points_ppr/F2_efficiency/tuned_tree | deep | 175 | 37 | 63.0 |
| A_2024/fantasy_points_ppr/F3_role_pbp/old_tree | 1 | 200 | 20 | 31.0 |
| A_2024/fantasy_points_ppr/F3_role_pbp/tuned_tree | fast | 125 | 5 | 18.9 |
| B_2025/targets/F2_efficiency/old_tree | 1 | 200 | 20 | 31.0 |
| B_2025/targets/F2_efficiency/tuned_tree | deep | 175 | 29 | 63.0 |
| B_2025/targets/F3_role_pbp/old_tree | 0 | 150 | 12 | 15.0 |
| B_2025/targets/F3_role_pbp/tuned_tree | deep | 225 | 30 | 63.0 |
| B_2025/carries/F2_efficiency/old_tree | 1 | 200 | 20 | 31.0 |
| B_2025/carries/F2_efficiency/tuned_tree | slow | 400 | 5 | 17.8 |
| B_2025/carries/F3_role_pbp/old_tree | 0 | 150 | 12 | 15.0 |
| B_2025/carries/F3_role_pbp/tuned_tree | regularized | 200 | 5 | 13.1 |
| B_2025/fantasy_points_ppr/F2_efficiency/old_tree | 0 | 150 | 12 | 15.0 |
| B_2025/fantasy_points_ppr/F2_efficiency/tuned_tree | deep | 100 | 26 | 63.0 |
| B_2025/fantasy_points_ppr/F3_role_pbp/old_tree | 1 | 200 | 17 | 31.0 |
| B_2025/fantasy_points_ppr/F3_role_pbp/tuned_tree | fast | 125 | 5 | 20.8 |
| C_2025/targets/F2_efficiency/old_tree | 1 | 200 | 19 | 31.0 |
| C_2025/targets/F2_efficiency/tuned_tree | deep | 125 | 28 | 63.0 |
| C_2025/targets/F3_role_pbp/old_tree | 1 | 200 | 17 | 31.0 |
| C_2025/targets/F3_role_pbp/tuned_tree | flexible | 225 | 8 | 30.8 |
| C_2025/carries/F2_efficiency/old_tree | 1 | 200 | 20 | 31.0 |
| C_2025/carries/F2_efficiency/tuned_tree | shallow | 375 | 3 | 7.1 |
| C_2025/carries/F3_role_pbp/old_tree | 1 | 200 | 21 | 31.0 |
| C_2025/carries/F3_role_pbp/tuned_tree | regularized | 400 | 5 | 13.3 |
| C_2025/fantasy_points_ppr/F2_efficiency/old_tree | 0 | 150 | 11 | 15.0 |
| C_2025/fantasy_points_ppr/F2_efficiency/tuned_tree | shallow | 125 | 3 | 7.7 |
| C_2025/fantasy_points_ppr/F3_role_pbp/old_tree | 0 | 150 | 11 | 15.0 |
| C_2025/fantasy_points_ppr/F3_role_pbp/tuned_tree | shallow | 275 | 3 | 7.4 |

## Interpretation and artifacts

Compare each fixed neural cell separately. Selecting the best neural family/method in a target column after seeing assessment is descriptive best-of-column, not a frozen selector. Tree search received eight chronological-stopped configurations versus two old-tree and prior-neural configurations; this cannot establish intrinsic architecture superiority. The independently running capacity study has a separate freeze.

Deeper trees can reduce training error while worsening later validation. learning_curves.csv retains every25iteration training/stopping error and normalized stopping score; summary.json records selected actual depths/leaves, runtime and paired deltas versus each neural comparator. results.json retains position, outcome-defined high-workload/workload-shift, sparse-history, team-change, empirical90%interval, PPR upside and samegame pair-ranking diagnostics. Outcome-defined subgroups never enter features.

Selection uses historical stopping/select partitions only, with train-only preprocessing. Twelve dependent weeks, previously inspected outcomes, reconstructed revised source chronology and observed-participant conditioning limit robustness. Week bootstrap intervals are descriptive; they do not establish independent-player significance. MAE/ranking improvements do not establish lineup return or profitability. A positive result warrants a separately frozen prospective, time-safe scoring/participation and production-pipeline parity study before promotion.

All 36 selected checkpoints reloaded and exactly reproduced 33,072 row predictions (maximum difference <1e-10). F3 unchanged-tree controls match the independently frozen fullprecision context baseline within 4.99e-09. F3 residual/position comparisons reuse exact-context baseline; F2 and prior_nn reuse V4 rounded matrix/prediction files; identical canonical rows/features, minor numeric precision distinction preserved.

Reproduce by copying this directory to a new versioned destination, clearing only newly copied derived output, preserving SPECIFICATION.md/run.py and validating the frozen dependency hashes, then run .venv/bin/python <copy>/run.py and report.py. The runner refuses an existing freeze. Frozen source lineage remains in upstream context receipts and is hashed by freeze.json.
