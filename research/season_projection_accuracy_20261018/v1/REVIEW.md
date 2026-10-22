# 2026 season-to-date projection accuracy — observed contest cohort

Read-only retrospective audit, 2026-10-18 America/Denver. No training, projections, user settings, lineups, or selection policies changed. Sunday scenario generation remains paused before implementation.

Across 2,200 unique canonical player-games from 71 completed games in Weeks 1–6, stored pregame forecasts miss by 4.07 DK points on average. The forecast>=5 cohort is more relevant to normal lineup decisions: 978 player-games, MAE 6.25, RMSE 8.09, bias −0.74. Negative bias means underprojection. Whole-pool accuracy is flattered by low-forecast bench players.

This is a descriptive audit of physically stored pregame predictions, **not a fully source/code-verified historical backtest**. Independent original-source capture chronology and execution of the exact original code were not verified for every forecast. Strict verified aggregate: unavailable (0 certified rows, not 0 predictions). Do not infer that current projections were backtested throughout the season.

## Measurement contract

- Canonical identity only; no raw display-name joins. One player-game across all contests, formats, and slates. Captain actual points divided by 1.5; unmultiplied player projections. Conditional Analyst scores excluded.
- Latest projection physically stored before that game kickoff, with projection-run and model-run creation before kickoff and data cutoff no later than creation; ties deterministic by row creation and run ID. This policy does not prove these projections were selected for any specific entered lineup.
- Kickoff from raw NFL schedule native game ID. Schedule was ingested after some games; used only to identify lock timing, not as a generation feature. Historical source availability remains unverified.
- All 55 linked contest source files were located and SHA-verified, using inner CSV hash where the import recorded normalized CSV bytes rather than ZIP bytes. Every nonblank TimeRemaining was 0. No future or in-progress result treated as 0. Source completion inventory retained.
- Actuals are observed official DraftKings standings points, not a reconstructed PPR proxy. DST uses observed DK totals, avoiding incorrect points-allowed reconstruction; existing dedicated target.fact_player_game_actual and fact_dst_game_actual have no 2026 rows.
- 2,739 canonical actual player-games identified; 2,200 have matching admissible stored forecasts (80.3%). 196 source observations lacked a unique canonical salary-to-game mapping and were excluded; repeated observations are not independent games. No conflicting cross-contest base actuals detected at 0.025-point tolerance. 112 forecast variants failed physical pregame/cutoff checks, not 112 unique player-games.
- Fixed regular forecast cohort: predicted mean >=5 DK points, selected without actual-score filtering. It is a forecast-size cohort, not verified starter/role eligibility and not a universal user salary rule. Legitimate actual zeros stay included. No rolling baseline superiority claimed: a same-cohort, time-safe historical baseline was not recomputed.
- Individual P90 exceedance target is approximately 10%; nominal P10–P90 coverage approximately 80%, with discreteness/zero truncation relevant. These are marginal intervals, not joint lineup probabilities. Games and teammates are correlated; no independent-row significance claim.

## Aggregate

| Cohort | Player-games | MAE | RMSE | Bias | Actual > P90 | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| All matched | 2200 | 4.07 | 6.03 | -0.19 | 10.5% | 82.1% |
| Forecast >=5 | 978 | 6.25 | 8.09 | -0.74 | 14.0% | 73.5% |

## Weekly trend (forecast >=5)

| Week (all-cohort games) | Player-games | MAE | RMSE | Bias | Actual > P90 | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| 1 (14 games) | 184 | 6.65 | 8.71 | -1.29 | 19.0% | 66.8% |
| 2 (3 games) | 46 | 8.11 | 10.34 | -2.11 | 26.1% | 58.7% |
| 3 (13 games) | 177 | 5.60 | 7.09 | -0.36 | 11.3% | 76.3% |
| 4 (15 games) | 214 | 6.16 | 8.22 | -0.84 | 13.1% | 72.9% |
| 5 (14 games) | 188 | 6.52 | 8.43 | -1.13 | 13.8% | 78.2% |
| 6 (12 games) | 169 | 5.82 | 7.08 | +0.38 | 9.5% | 77.5% |

Week 2 covers only 3 games: it is not a complete weekly comparison. Week 6 covers 12 completed games with result/forecast overlap; no Sunday Night or Monday outcome is assumed. Different coverage and model versions prevent interpreting this as a controlled learning curve.

## Position breakdown (forecast >=5)

| Position | Player-games | MAE | RMSE | Bias | Actual > P90 | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| QB | 142 | 6.84 | 8.84 | -1.35 | 14.8% | 78.2% |
| RB | 230 | 6.67 | 8.48 | -0.89 | 15.2% | 66.5% |
| WR | 362 | 6.41 | 8.36 | -0.37 | 12.2% | 74.6% |
| TE | 148 | 6.14 | 7.72 | -1.00 | 17.6% | 70.3% |
| K | 26 | 3.99 | 5.28 | +0.07 | 15.4% | 80.8% |
| DST | 70 | 3.96 | 4.83 | -0.67 | 10.0% | 85.7% |

All-cohort position counts QB246/RB487/WR800/TE484/K29/DST120. Another 34 canonical players have FB/CB/DB/DT/LB/LS/FLEX master positions and remain visible in the JSON rather than silently reassigned. The forecast>=5 cohort consists entirely of the six reported positions. K is a small sample.

## Original model versions, not current-model backfill

| Stored model | Player-games | MAE | RMSE | Bias | Actual > P90 | P10–P90 coverage |
|---|---:|---:|---:|---:|---:|---:|
| gradient_boosting_active_v3_position_role | 19 | 2.33 | 3.58 | +2.25 | 0.0% | 94.7% |
| gradient_boosting_challenger_v4_1_team_opportunity_context | 462 | 4.18 | 6.34 | -0.53 | 12.6% | 80.5% |
| gradient_boosting_challenger_v4_2_market_corrected | 1005 | 3.91 | 5.95 | -0.16 | 9.3% | 84.0% |
| gradient_boosting_challenger_v4_2_market_corrected+verified_dst_serving_component_v1:ensemble | 294 | 4.35 | 5.95 | -0.07 | 11.2% | 81.3% |
| gradient_boosting_challenger_v4_2_role_opportunity | 420 | 4.23 | 5.99 | -0.10 | 11.4% | 79.3% |

Versions are evaluated on different games and cohorts. These are not head-to-head superiority results. The current verified-DST ensemble has only 294 matched rows /11 games here; its forecast>=5 subset150 has MAE5.79, bias+0.22, P90 exceed10.0%, intervalcoverage77.3%. This is not season-long current-model validation.

## Evidence-backed diagnosis and next tests

1. **Small whole-pool bias hides decision-relevant error.** The regular forecast cohort misses by 6.25 points, versus whole-pool4.07. Report both permanently; do not optimize claims against bench-heavy aggregate MAE.
2. **The regular cohort upper tail is too low descriptively:** actuals exceed P90 in14.0%, and central intervals cover73.5%. TE (17.6% exceed;70.3% interval) and RB (15.2%;66.5%) deserve prospective, position/role-stratified calibration checks. This does not establish an automatic universal upward shift; actual cohort/model/game mix and zero mass differ.
3. **QBs underproject by1.35 points in the >=5 cohort**, with MAE6.84 (142 rows). Investigate role, rushing, game environment and available context on repeated misses before altering coefficients. WR average bias−0.37 but MAE6.41 demonstrates cancellation of large errors.
4. **This Sunday was not the worst point-forecast week in the observed regular cohort:** W6MAE5.82 versusW5 6.52/W1 6.65. W6bias+0.38 also differs from the season regular underprojection. Poor entered results can coexist with reasonable pool accuracy because candidate coverage, selected support combinations and correlated game failures matter; this audit alone cannot attribute optimizer loss to projections.
5. First measurement repair is a persistent unique player-game forecast/actual evaluation with verified predecision source receipts, exact model/feature lineage, and coverage/missingness. Then test calibration prospectively on the same cohorts, separate from scenario-generation improvements. No threshold/forecast changes are justified merely by these retrospective errors.

## Largest absolute misses (examples, not policy targets)

| Week | Player | Forecast | Actual | Error forecast−actual |
|---|---|---:|---:|---:|
| 4 | Tetairoa McMillan | 10.80 | 48.20 | -37.40 |
| 2 | Davante Adams | 12.58 | 42.50 | -29.92 |
| 5 | Drake Maye | 16.09 | 42.46 | -26.37 |
| 4 | Tyquan Thornton | 4.86 | 31.10 | -26.24 |
| 1 | Jalen Coker | 11.50 | 36.80 | -25.30 |
| 5 | Jaylen Warren | 14.90 | 39.80 | -24.90 |
| 5 | Christian Watson | 10.83 | 35.30 | -24.47 |
| 4 | CeeDee Lamb | 19.88 | 44.30 | -24.42 |
| 1 | Christian Watson | 11.72 | 35.70 | -23.98 |
| 1 | D'Andre Swift | 11.54 | 35.40 | -23.86 |
| 3 | Jahmyr Gibbs | 18.49 | 41.40 | -22.91 |
| 5 | Malik Nabers | 9.39 | 32.10 | -22.71 |

Large TD/efficiency outcomes are not proof their exact outcomes should have been forecast. No outcome-tuned selection or scenario features were added. A systematic team/correlation model failure is not established from this bounded analysis; teammates are dependent and team-level opportunity evidence needs separate review.

Files: summary.json (metrics and limitations), player_games.json (one selected forecast per canonical game/player), source_completion.json (source hashes/paths/time checks), analyze.py (read-only local extraction consumer). Raw DB extracts remain /private/tmp/season_accuracy_20261018. Original learning reports and source snapshots unchanged.
