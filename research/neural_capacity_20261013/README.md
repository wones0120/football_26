# Wider/deeper neural capacity comparison

Larger neural nets yielded modest average-error gains for the shared residual design, with mixed results for position-aware heads. On F3, expanded residual MAE improved targets 1.4192→1.3949, carries 1.2771→1.2415, and source PPR 4.6604→4.6387. Tuned tree remains lower in carries/PPR MAE (1.2062/4.5750); the neural target advantage is small and its paired interval overlaps zero. Capacity carries/PPR RMSE rose slightly, and high-workload MAE worsened for all three targets. These results do not support automatic promotion.

This research changed no live projections, application defaults, or database records. It is retrospective development on previously inspected historical outcomes. Inputs are full precision, features/rows/chronological folds are identical to the concurrent tree experiment. Source PPR is not DraftKings scoring; the observed participant cohort does not model DNP risk. No W6+ outcomes were accessed.

216 macro fits completed in 341.8s elapsed wall time with one native thread; 864 trained heads. No architecture was selected using assessment outcomes. Current NN searches 2 controls; expanded NN searches 6 options including controls; tuned tree searches 8 joint configs. Different search/training budgets prevent intrinsic architecture superiority claims.

MAE / RMSE / bias by target, fixed feature family and whole selected model:

| Target | Features | Model | MAE | RMSE | Bias |
|---|---|---|---:|---:|---:|
| carries | F2_efficiency | capacity_position_nn | 1.2766 | 2.6609 | +0.1406 |
| carries | F2_efficiency | capacity_residual_nn | 1.2233 | 2.6915 | -0.2353 |
| carries | F2_efficiency | current_position_nn | 1.2822 | 2.7137 | +0.0567 |
| carries | F2_efficiency | current_residual_nn | 1.2233 | 2.6915 | -0.2353 |
| carries | F2_efficiency | old_tree | 1.2157 | 2.5151 | +0.0338 |
| carries | F2_efficiency | tuned_tree | 1.2066 | 2.5014 | +0.0377 |
| carries | F3_role_pbp | capacity_position_nn | 1.2502 | 2.6059 | +0.1041 |
| carries | F3_role_pbp | capacity_residual_nn | 1.2415 | 2.5438 | -0.0054 |
| carries | F3_role_pbp | current_position_nn | 1.2502 | 2.6059 | +0.1041 |
| carries | F3_role_pbp | current_residual_nn | 1.2771 | 2.5169 | +0.0689 |
| carries | F3_role_pbp | old_tree | 1.2135 | 2.4987 | +0.0295 |
| carries | F3_role_pbp | tuned_tree | 1.2062 | 2.4840 | +0.0357 |
| fantasy_points_ppr | F2_efficiency | capacity_position_nn | 4.8318 | 6.5899 | +0.0528 |
| fantasy_points_ppr | F2_efficiency | capacity_residual_nn | 4.7061 | 6.3832 | +0.2804 |
| fantasy_points_ppr | F2_efficiency | current_position_nn | 4.7857 | 6.5166 | +0.2091 |
| fantasy_points_ppr | F2_efficiency | current_residual_nn | 4.7343 | 6.4225 | +0.2497 |
| fantasy_points_ppr | F2_efficiency | old_tree | 4.6324 | 6.2802 | +0.2222 |
| fantasy_points_ppr | F2_efficiency | tuned_tree | 4.6654 | 6.3225 | +0.2337 |
| fantasy_points_ppr | F3_role_pbp | capacity_position_nn | 4.7580 | 6.4514 | +0.1861 |
| fantasy_points_ppr | F3_role_pbp | capacity_residual_nn | 4.6387 | 6.3329 | +0.1423 |
| fantasy_points_ppr | F3_role_pbp | current_position_nn | 4.8208 | 6.5333 | +0.1610 |
| fantasy_points_ppr | F3_role_pbp | current_residual_nn | 4.6604 | 6.3317 | +0.2747 |
| fantasy_points_ppr | F3_role_pbp | old_tree | 4.5759 | 6.2213 | +0.2895 |
| fantasy_points_ppr | F3_role_pbp | tuned_tree | 4.5750 | 6.2188 | +0.2220 |
| targets | F2_efficiency | capacity_position_nn | 1.4420 | 2.0721 | +0.1148 |
| targets | F2_efficiency | capacity_residual_nn | 1.4142 | 1.9945 | +0.0838 |
| targets | F2_efficiency | current_position_nn | 1.4451 | 2.0707 | +0.0978 |
| targets | F2_efficiency | current_residual_nn | 1.4328 | 2.0117 | +0.0877 |
| targets | F2_efficiency | old_tree | 1.4308 | 2.0164 | +0.1019 |
| targets | F2_efficiency | tuned_tree | 1.4293 | 2.0086 | +0.1135 |
| targets | F3_role_pbp | capacity_position_nn | 1.4440 | 2.0731 | +0.0606 |
| targets | F3_role_pbp | capacity_residual_nn | 1.3949 | 1.9771 | +0.0249 |
| targets | F3_role_pbp | current_position_nn | 1.4223 | 2.0253 | +0.0701 |
| targets | F3_role_pbp | current_residual_nn | 1.4192 | 2.0005 | +0.0761 |
| targets | F3_role_pbp | old_tree | 1.4121 | 1.9798 | +0.1136 |
| targets | F3_role_pbp | tuned_tree | 1.4097 | 1.9954 | +0.1002 |

Paired capacity-minus-current MAE differences (negative favors capacity), with descriptive week-cluster intervals:

| Target | Features | Design | ΔMAE | 95% interval | Weeks win/tie/loss |
|---|---|---|---:|---|---|
| carries | F2_efficiency | residual_nn | +0.0000 | [+0.0000, +0.0000] | 0/12/0 |
| carries | F2_efficiency | position_nn | -0.0056 | [-0.0512, +0.0438] | 7/0/5 |
| carries | F3_role_pbp | residual_nn | -0.0357 | [-0.0673, -0.0039] | 8/0/4 |
| carries | F3_role_pbp | position_nn | +0.0000 | [+0.0000, +0.0000] | 0/12/0 |
| fantasy_points_ppr | F2_efficiency | residual_nn | -0.0281 | [-0.0707, +0.0063] | 3/8/1 |
| fantasy_points_ppr | F2_efficiency | position_nn | +0.0460 | [-0.0168, +0.1076] | 4/0/8 |
| fantasy_points_ppr | F3_role_pbp | residual_nn | -0.0218 | [-0.0566, +0.0172] | 7/0/5 |
| fantasy_points_ppr | F3_role_pbp | position_nn | -0.0627 | [-0.1601, +0.0413] | 7/4/1 |
| targets | F2_efficiency | residual_nn | -0.0186 | [-0.0351, -0.0023] | 6/4/2 |
| targets | F2_efficiency | position_nn | -0.0031 | [-0.0229, +0.0191] | 3/8/1 |
| targets | F3_role_pbp | residual_nn | -0.0243 | [-0.0434, -0.0056] | 9/0/3 |
| targets | F3_role_pbp | position_nn | +0.0217 | [+0.0029, +0.0421] | 1/4/7 |

For F3 residual heads, high-workload MAE rose targets 2.6424→2.7025, carries 4.5034→4.6999, and PPR 8.6887→8.8983. Large realized workload-shift rows also worsened on average. These outcome-defined subsets are diagnostics and cannot serve as predecision selectors.

Only 12 week clusters and overlapping historical training windows make these intervals exploratory. Subgroups, all per-week errors, paired neural-minus-tree differences, PPR rank/upside diagnostics, and individual-architecture errors are in summary.json. Individual-architecture assessment diagnostics were computed after the selection freeze and cannot justify selecting a different model.

Largest individual head has 26,241 learned parameters. 0 heads reached their epoch cap; 0 recorded warnings. learning_curves.csv retains every training-loss, standardized training metric and stopping metric; head_training_diagnostics.csv retains best epochs, head runtimes and counts. The residual stopping metric is raw target MAE while its training_metric is standardized residual RMSE; do not directly subtract those two columns. Position amount heads use standardized log-amount RMSE and classifier heads use Brier; raw macro training/stopping MAE is in results.json.

Training summary across three mixed target units is descriptive only; compare within target/family using the full per-fit results. Wider/deeper options that lower training error without consistent assessment gains suggest overfitting/variance under this setup; a stopped curve does not rule out an optimization issue.

Current architecture and larger architecture checkpoints plus all prespecified selection scores are stored in models/ and results.json. Original V4 files remain untouched. Training budgets are bounded; converged stopping or local training-loss reduction alone does not prove sufficient capacity or optimization globally. Width/depth comparisons preserve features, but widest 128-unit option jointly changes regularization/LR and larger candidates permit more epochs.

No automatic promotion is recommended from this retrospective search. Reserve prospective W6+ protocol with forecasts frozen before decision/lock, compare one fully specified whole model under identical input/cohort and scoring rules, then consider live changes only if repeatable gains appear.

PPR ranking diagnostics on F3: macro-average NDCG across 48 season-week-position cells is current residual .6426, capacity residual .6366, tuned tree .6367; boom precision is .2870/.2748/.2804. These are descriptive point-ranking diagnostics, not calibrated ceilings, joint portfolios, or contest-profit evidence.

Verification: 5 targeted tests passed. 72 selected serialized-model cells replay exactly; 12 real-data controls match the untouched V4 functions exactly. All 36 current choices match original frozen V4 choices. Fullprecision source hash, F2/F3 features and folds match the tree experiment; joins retain exact player/fold rows.

Run targeted checks from the repository root with `PYTHONPATH=. .venv/bin/python -m pytest research/neural_capacity_20261013/test_capacity.py -q`; replay saved artifacts with `PYTHONPATH=. .venv/bin/python research/neural_capacity_20261013/verify.py`. Training refuses to overwrite an existing freeze; reproduce in a separately named research directory with identical frozen source dependencies. `report.py` recomputes descriptive comparison from frozen predictions and does not train or select models.
