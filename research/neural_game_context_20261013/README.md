# Neural game-context experiment

Schedule context helped one specific neural task: full-feature residual carries MAE 1.277 → 1.228, about 3.9%, with lower error in all 12 assessment weeks. Target error improved about 1.1%; PPR did not improve. Combined context did not establish a broad neural advantage. No model or input family was promoted. This is retrospective revised-data development, not an untouched or prospective validation.

## Paired pooled prediction error

Each cell is baseline → combined context MAE; lower is better. Same cohort, features apart from declared treatment, seed, chronological folds and two configuration choices per arm.

| Method | Targets | Carries | Source PPR |
|---|---:|---:|---:|
| residual_nn | 1.419 → 1.404 | 1.277 → 1.266 | 4.660 → 4.712 |
| position_nn | 1.422 → 1.457 | 1.250 → 1.304 | 4.821 → 4.895 |
| tree | 1.412 → 1.400 | 1.213 → 1.220 | 4.576 → 4.565 |

## Individual families

| Method / target | Baseline | Schedule | Venue | Teammate proxy | Opponent proxy | Combined |
|---|---:|---:|---:|---:|---:|---:|
| residual_nn / targets | 1.419 | 1.403 | 1.403 | 1.406 | 1.411 | 1.404 |
| residual_nn / carries | 1.277 | 1.228 | 1.255 | 1.260 | 1.271 | 1.266 |
| residual_nn / fantasy_points_ppr | 4.660 | 4.680 | 4.682 | 4.672 | 4.668 | 4.712 |
| position_nn / targets | 1.422 | 1.433 | 1.467 | 1.460 | 1.468 | 1.457 |
| position_nn / carries | 1.250 | 1.314 | 1.378 | 1.372 | 1.376 | 1.304 |
| position_nn / fantasy_points_ppr | 4.821 | 4.856 | 5.024 | 4.914 | 4.928 | 4.895 |
| tree / targets | 1.412 | 1.408 | 1.411 | 1.408 | 1.422 | 1.400 |
| tree / carries | 1.213 | 1.207 | 1.218 | 1.215 | 1.211 | 1.220 |
| tree / fantasy_points_ppr | 4.576 | 4.559 | 4.570 | 4.566 | 4.592 | 4.565 |

## Paired week uncertainty

Combined minus baseline absolute error, with descriptive whole-week bootstrap 95% bounds. Negative means improvement. Twelve week blocks are few and dependent; intervals do not repair previous outcome inspection or select a confirmed winner. Schedule-only residual carries had paired difference −0.0493, descriptive95% bounds[−0.0657,−0.0335], improving12/12weeks.

| Method / target | Difference | 95% bounds | Improved weeks |
|---|---:|---:|---:|
| residual_nn / targets | -0.016 | [-0.041, +0.009] | 7/12 |
| residual_nn / carries | -0.011 | [-0.037, +0.013] | 6/12 |
| residual_nn / fantasy_points_ppr | +0.052 | [-0.002, +0.101] | 2/12 |
| position_nn / targets | +0.034 | [-0.003, +0.071] | 5/12 |
| position_nn / carries | +0.054 | [+0.011, +0.100] | 3/12 |
| position_nn / fantasy_points_ppr | +0.075 | [-0.013, +0.160] | 3/12 |
| tree / targets | -0.013 | [-0.026, +0.002] | 9/12 |
| tree / carries | +0.006 | [-0.007, +0.021] | 5/12 |
| tree / fantasy_points_ppr | -0.011 | [-0.046, +0.029] | 8/12 |

## Inputs actually used

- 13 schedule inputs: home/neutral, cyclical weekday and ET/venue-local kickoff, >=19ET flag, own/opponent calendar rest and <=5day short rest. IANA timezones handle DST; neutral home is unknown; contradictory JAX00 international ID local time is unknown. Rest is derived from earlier regular-season game dates; first-week rest unknown.
- Four venue inputs: fixed covered, open air, retractable and unknown, inferred solely from earlier completed games at the stadium ID. Target roof/weather never enters the inputs. Retractable operational roof stays unknown. This measures structural venue context, not actual game roof position.
- Ten teammate plus ten opponent inputs: prior-three-game history count, previously observed target/carry workload absent or returning in the last completed game, QB historical participant counts, OL/defender prior snap workload absent in the last completed game, and canonical snap identity coverage. Teammate aggregates exclude the focal player. Names never join records; historical team/position and native bridge control identity.

The paired baseline here is the full F3 68-input model. Earlier V4 F2 residual carries MAE 1.223 remains slightly better than this F3+schedule result 1.228; these context results do not demonstrate improvement over every earlier neural configuration. Trees still have lower pooled carry/PPR errors.

These are lagged participation proxies, not upcoming availability. Workload sums are observed lower bounds: unknown stat contributions are omitted, not inferred as healthy or absent. QB counts measure continuity rather than a forecast of who starts. OL/defender signals include only canonically resolved historical players; coverage remains visible. Missing group evidence remains NaN. Current registry statuses, target-game participant lists and target-game teammate/opponent scores never enter context.

## Actual availability: implemented contract, unsupported experiment

availability.py exposes a scoring-only contract for original source receipts: game ID, source identifier/hash, publication and observed clocks before cutoff, effective canonical roster, report status, prior-game workload clock, and known opponent. Missing reports stay unknown. Out, doubtful and questionable remain distinct. Explicit prior out → current available can identify return counts; no realized DNP probability is fabricated. Synthetic contract fixtures verify this behavior; no historical availability model has been validated.

| Captured source | Rows | Update timestamp | Original predecision receipt | Primary training |
|---|---:|---|---|---|
| nflverse injuries2023 | 5599 | yes | missing | excluded |
| nflverse injuries2024 | 6215 | yes | missing | excluded |
| nflverse injuries2025 | 6068 | no | missing | excluded |

All 2023/24/25 injury records resolved to existing canonical native-ID mappings. That resolves identity, not chronology. Revised 2023/24 date_modified is an update clock, not a preserved original publication/capture receipt; 2025 has no update clock. No primary experiment used injury-status inputs. Inventory and immutably hashed downloads are retained separately.

Official source documentation: [injury dictionary](https://nflreadr.nflverse.com/articles/dictionary_injuries.html) and [data update schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html). The actual downloaded schema, not a stale search snippet, determines timestamp coverage.

## Feature coverage

| Input | Nonmissing rows | Coverage |
|---|---:|---:|
| ctx_home | 21538/22065 | 97.6% |
| ctx_neutral | 22065/22065 | 100.0% |
| ctx_weekday_sin | 22065/22065 | 100.0% |
| ctx_weekday_cos | 22065/22065 | 100.0% |
| ctx_et_sin | 22065/22065 | 100.0% |
| ctx_et_cos | 22065/22065 | 100.0% |
| ctx_local_sin | 22013/22065 | 99.8% |
| ctx_local_cos | 22013/22065 | 99.8% |
| ctx_prime_time | 22065/22065 | 100.0% |
| ctx_rest_days | 20491/22065 | 92.9% |
| ctx_opponent_rest_days | 20491/22065 | 92.9% |
| ctx_short_rest | 20491/22065 | 92.9% |
| ctx_opponent_short_rest | 20491/22065 | 92.9% |
| ctx_fixed_indoor | 22065/22065 | 100.0% |
| ctx_open_air | 22065/22065 | 100.0% |
| ctx_retractable | 22065/22065 | 100.0% |
| ctx_venue_unknown | 22065/22065 | 100.0% |
| ctx_teammate_history_games | 22065/22065 | 100.0% |
| ctx_teammate_receiving_absent_last_targets | 18914/22065 | 85.7% |
| ctx_teammate_rushing_absent_last_carries | 18914/22065 | 85.7% |
| ctx_teammate_receiving_returned_last_targets | 17330/22065 | 78.5% |
| ctx_teammate_rushing_returned_last_carries | 17330/22065 | 78.5% |
| ctx_teammate_qb_prior_count | 18914/22065 | 85.7% |
| ctx_teammate_qb_last_count | 20491/22065 | 92.9% |
| ctx_teammate_ol_absent_last_snaps | 18914/22065 | 85.7% |
| ctx_teammate_defense_absent_last_snaps | 18914/22065 | 85.7% |
| ctx_teammate_canonical_snap_coverage | 20491/22065 | 92.9% |
| ctx_opponent_history_games | 22065/22065 | 100.0% |
| ctx_opponent_receiving_absent_last_targets | 18914/22065 | 85.7% |
| ctx_opponent_rushing_absent_last_carries | 18914/22065 | 85.7% |
| ctx_opponent_receiving_returned_last_targets | 17330/22065 | 78.5% |
| ctx_opponent_rushing_returned_last_carries | 17330/22065 | 78.5% |
| ctx_opponent_qb_prior_count | 18914/22065 | 85.7% |
| ctx_opponent_qb_last_count | 20491/22065 | 92.9% |
| ctx_opponent_ol_absent_last_snaps | 18914/22065 | 85.7% |
| ctx_opponent_defense_absent_last_snaps | 18914/22065 | 85.7% |
| ctx_opponent_canonical_snap_coverage | 20491/22065 | 92.9% |

Coverage is over all original matrix rows, not solely labeled Sunday assessment rows. coverage.json retains every game/team canonical snap bridge count. context_lineage.json retains prior games and cutoff for every matrix row; verification rejects target-game history references. Schedule/venue histories are reconstructed from revised releases captured after old decision times and may include revised schedule metadata; they do not establish original pregame evidence.

## Position results and subgroup limits

| Method / target / position | n | Baseline MAE | Combined MAE | Combined bias |
|---|---:|---:|---:|---:|
| residual_nn / targets / RB | 670 | 1.298 | 1.311 | +0.063 |
| residual_nn / targets / QB | 321 | 0.151 | 0.130 | +0.095 |
| residual_nn / targets / WR | 1139 | 1.809 | 1.787 | +0.145 |
| residual_nn / targets / TE | 626 | 1.490 | 1.458 | +0.093 |
| residual_nn / carries / RB | 670 | 3.582 | 3.609 | -0.134 |
| residual_nn / carries / QB | 321 | 1.920 | 1.785 | -0.097 |
| residual_nn / carries / WR | 1139 | 0.310 | 0.293 | +0.082 |
| residual_nn / carries / TE | 626 | 0.239 | 0.263 | +0.075 |
| residual_nn / fantasy_points_ppr / RB | 670 | 4.815 | 4.738 | +0.194 |
| residual_nn / fantasy_points_ppr / QB | 321 | 6.624 | 6.830 | +0.088 |
| residual_nn / fantasy_points_ppr / WR | 1139 | 4.543 | 4.604 | +0.193 |
| residual_nn / fantasy_points_ppr / TE | 626 | 3.702 | 3.794 | +0.171 |
| position_nn / targets / RB | 670 | 1.357 | 1.364 | +0.205 |
| position_nn / targets / QB | 321 | 0.031 | 0.032 | -0.005 |
| position_nn / targets / WR | 1139 | 1.812 | 1.867 | +0.202 |
| position_nn / targets / TE | 626 | 1.497 | 1.539 | +0.058 |
| position_nn / carries / RB | 670 | 3.717 | 3.933 | +0.594 |
| position_nn / carries / QB | 321 | 1.824 | 1.843 | -0.021 |
| position_nn / carries / WR | 1139 | 0.234 | 0.235 | +0.024 |
| position_nn / carries / TE | 626 | 0.165 | 0.158 | -0.079 |
| position_nn / fantasy_points_ppr / RB | 670 | 4.982 | 5.106 | +0.361 |
| position_nn / fantasy_points_ppr / QB | 321 | 7.045 | 7.108 | -0.521 |
| position_nn / fantasy_points_ppr / WR | 1139 | 4.623 | 4.712 | +0.043 |
| position_nn / fantasy_points_ppr / TE | 626 | 3.868 | 3.869 | -0.075 |
| tree / targets / RB | 670 | 1.315 | 1.304 | +0.107 |
| tree / targets / QB | 321 | 0.080 | 0.086 | +0.051 |
| tree / targets / WR | 1139 | 1.817 | 1.801 | +0.124 |
| tree / targets / TE | 626 | 1.463 | 1.445 | +0.112 |
| tree / carries / RB | 670 | 3.623 | 3.638 | +0.031 |
| tree / carries / QB | 321 | 1.719 | 1.734 | +0.062 |
| tree / carries / WR | 1139 | 0.231 | 0.230 | +0.006 |
| tree / carries / TE | 626 | 0.164 | 0.168 | -0.014 |
| tree / fantasy_points_ppr / RB | 670 | 4.649 | 4.668 | +0.114 |
| tree / fantasy_points_ppr / QB | 321 | 6.491 | 6.523 | -0.012 |
| tree / fantasy_points_ppr / WR | 1139 | 4.467 | 4.458 | +0.230 |
| tree / fantasy_points_ppr / TE | 626 | 3.714 | 3.644 | +0.100 |

Full fold metrics retain home/neutral/retractable/rest/missing-prior-workload subgroups, position/high workload errors, bias, empirical intervals and predefined PPR upside rankings. Subgroups with little or no coverage cannot support an effect claim. Assessment is Sunday Main, so weekday/prime-time have limited assessment variation; those features still vary in training. The model remains conditional on retrospectively observed positive snaps, excluding DNP rather than forecasting participation. Source PPR is not DraftKings scoring. Point errors/rankings do not validate portfolios, correlated lineup outcomes or profitability.

## Reproduction and verification

324 fixed configuration fits completed in 556.4s; selected checkpoints saved for all 162 fold/target/arm/method fits. Residual/history anchoring and position hurdle/log-workload networks use V4 train-only preprocessing and whole-week stopping; trees receive identical treatment inputs. No new dependency or application change.

20 targeted context + reused V4 training tests passed. All 162 saved checkpoints reloaded; 148,824 row forecasts reproduce within floating point tolerance, and all 22,065 contextual rows have prior-game cutoff lineage verified. Frozen spec/code/source/matrix/prediction/model hashes are retained. Checkpoint replay reconstructs full floating precision from original frozen sources; the ten-significant-digit CSV alone can move tree split ties. feature_matrix_full_precision.parquet and exact_input_receipt.json preserve those exact inputs separately, without altering original results.

```sh
PYTHONPATH=. .venv/bin/python -m pytest research/neural_game_context_20261013/test_context.py research/neural_workload_benchmark_20261013/training_v4/test_training.py -q
.venv/bin/python research/neural_game_context_20261013/verify.py
.venv/bin/python research/neural_game_context_20261013/report.py
```

run.py refuses an existing results.json; reproduce full training in a separately versioned copy after validating upstream source hashes. Do not overwrite the frozen study or reinterpret inspected historical weeks as untouched. Existing V4 prospective 2026 W6–9 protocol remains unchanged; no future outcomes or production projections/defaults were loaded/altered.
