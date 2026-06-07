# Matchup Outcome Intelligence

- Source: `draftkings`  Seasons: `2024-2025`  Rows analyzed: `17342`

## Score Drivers (Effect Size)

| Position | Factor | Effect Ratio |
|---|---|---:|
| RB | salary_tier | 0.370 |
| WR | salary_tier | 0.323 |
| QB | salary_tier | 0.213 |
| TE | salary_tier | 0.172 |
| DST | spread_role | 0.099 |
| DST | salary_tier | 0.056 |
| DST | total_band | 0.019 |
| DST | spread_abs_band | 0.005 |
| RB | spread_role | 0.004 |
| QB | spread_role | 0.004 |
| QB | total_band | 0.004 |
| TE | spread_role | 0.003 |
| WR | total_band | 0.002 |
| TE | total_band | 0.002 |
| QB | defense_bucket | 0.001 |
| WR | spread_role | 0.001 |
| RB | total_band | 0.001 |
| RB | is_home | 0.000 |
| RB | defense_bucket | 0.000 |
| TE | defense_bucket | 0.000 |
| TE | spread_abs_band | 0.000 |
| WR | defense_bucket | 0.000 |
| RB | spread_abs_band | 0.000 |
| WR | spread_abs_band | 0.000 |
| WR | is_home | 0.000 |
| QB | spread_abs_band | 0.000 |
| TE | is_home | 0.000 |
| QB | is_home | 0.000 |

## Strongest Positive Context Signals (4x Hit Lift)

| View | Key | Count | Adj 4x Lift | Avg Pts | Avg Value |
|---|---|---:|---:|---:|---:|
| position_x_defense_bucket | RB|favorable | 1234 | 0.87pp | 3.80 | 0.68x |
| position_x_defense_bucket | QB|neutral | 710 | 0.69pp | 5.39 | 0.89x |
| position_x_defense_bucket | TE|unknown | 235 | 0.45pp | 2.64 | 0.70x |
| position_x_defense_bucket | WR|favorable | 2129 | 0.20pp | 3.15 | 0.65x |
| position_x_defense_bucket | QB|favorable | 736 | 0.13pp | 5.20 | 0.83x |
| position_x_defense_bucket | WR|neutral | 2052 | 0.09pp | 3.17 | 0.67x |
| position_x_defense_bucket | TE|neutral | 1170 | 0.02pp | 2.27 | 0.68x |
| position_x_defense_bucket | DST|unknown | 656 | 0.00pp | 5.71 | 1.83x |
| position_x_total_band_x_spread_role | QB|47-50.9|close | 155 | 2.22pp | 6.12 | 0.97x |
| position_x_total_band_x_spread_role | WR|51+|underdog | 138 | 1.30pp | 3.94 | 0.82x |
| position_x_total_band_x_spread_role | RB|42-46.9|underdog | 428 | 1.15pp | 3.99 | 0.69x |
| position_x_total_band_x_spread_role | WR|42-46.9|close | 578 | 1.07pp | 3.21 | 0.65x |
| position_x_total_band_x_spread_role | WR|47-50.9|big_underdog | 212 | 0.93pp | 3.79 | 0.69x |
| position_x_total_band_x_spread_role | QB|<42|underdog | 126 | 0.87pp | 4.66 | 0.84x |
| position_x_total_band_x_spread_role | TE|47-50.9|big_underdog | 116 | 0.73pp | 3.35 | 0.89x |
| position_x_total_band_x_spread_role | RB|47-50.9|big_underdog | 126 | 0.72pp | 4.79 | 0.73x |
| position_x_salary_tier_x_teammate_out_band | QB|mid|0 | 307 | 7.00pp | 14.72 | 2.32x |
| position_x_salary_tier_x_teammate_out_band | WR|mid|0 | 722 | 5.35pp | 10.47 | 1.80x |
| position_x_salary_tier_x_teammate_out_band | RB|premium|0 | 288 | 3.49pp | 14.53 | 1.68x |
| position_x_salary_tier_x_teammate_out_band | RB|mid|0 | 727 | 3.37pp | 8.77 | 1.49x |
| position_x_salary_tier_x_teammate_out_band | TE|mid|0 | 127 | 3.17pp | 11.77 | 2.09x |
| position_x_salary_tier_x_teammate_out_band | DST|mid|0 | 219 | 1.47pp | 6.10 | 2.00x |
| position_x_salary_tier_x_teammate_out_band | DST|cheap|0 | 250 | 0.94pp | 4.20 | 1.71x |
| position_x_salary_tier_x_teammate_out_band | WR|premium|0 | 360 | 0.72pp | 12.85 | 1.42x |

## Strongest Negative Context Signals (4x Hit Lift)

| View | Key | Count | Adj 4x Lift | Avg Pts | Avg Value |
|---|---|---:|---:|---:|---:|
| position_x_defense_bucket | QB|tough | 712 | -0.77pp | 4.91 | 0.79x |
| position_x_defense_bucket | RB|tough | 1202 | -0.56pp | 3.45 | 0.60x |
| position_x_defense_bucket | WR|unknown | 428 | -0.47pp | 2.71 | 0.50x |
| position_x_defense_bucket | RB|neutral | 1194 | -0.32pp | 3.59 | 0.60x |
| position_x_defense_bucket | WR|tough | 2073 | -0.17pp | 3.11 | 0.64x |
| position_x_defense_bucket | QB|unknown | 155 | -0.16pp | 4.45 | 0.74x |
| position_x_defense_bucket | TE|favorable | 1221 | -0.12pp | 2.24 | 0.64x |
| position_x_defense_bucket | RB|unknown | 251 | -0.04pp | 3.51 | 0.58x |
| position_x_total_band_x_spread_role | TE|47-50.9|big_favorite | 145 | -1.82pp | 1.44 | 0.39x |
| position_x_total_band_x_spread_role | WR|42-46.9|big_underdog | 488 | -1.35pp | 2.94 | 0.57x |
| position_x_total_band_x_spread_role | TE|<42|underdog | 209 | -1.28pp | 1.82 | 0.55x |
| position_x_total_band_x_spread_role | QB|47-50.9|underdog | 132 | -1.12pp | 5.31 | 0.73x |
| position_x_total_band_x_spread_role | RB|<42|favorite | 190 | -1.11pp | 3.33 | 0.62x |
| position_x_total_band_x_spread_role | TE|42-46.9|underdog | 416 | -0.87pp | 2.14 | 0.58x |
| position_x_total_band_x_spread_role | RB|47-50.9|big_favorite | 137 | -0.85pp | 2.67 | 0.43x |
| position_x_total_band_x_spread_role | TE|<42|close | 260 | -0.82pp | 1.91 | 0.56x |
| position_x_salary_tier_x_teammate_out_band | DST|premium|0 | 187 | -2.74pp | 7.29 | 1.79x |
| position_x_salary_tier_x_teammate_out_band | QB|premium|0 | 286 | -2.21pp | 8.71 | 0.85x |
| position_x_salary_tier_x_teammate_out_band | RB|cheap|0 | 2866 | -1.47pp | 1.20 | 0.30x |
| position_x_salary_tier_x_teammate_out_band | QB|cheap|0 | 1720 | -1.17pp | 2.81 | 0.56x |
| position_x_salary_tier_x_teammate_out_band | WR|cheap|0 | 5600 | -0.87pp | 1.54 | 0.44x |
| position_x_salary_tier_x_teammate_out_band | TE|cheap|0 | 3635 | -0.18pp | 1.83 | 0.60x |
| position_x_salary_tier_x_teammate_out_band | WR|premium|0 | 360 | 0.72pp | 12.85 | 1.42x |
| position_x_salary_tier_x_teammate_out_band | DST|cheap|0 | 250 | 0.94pp | 4.20 | 1.71x |

## Team-vs-Opponent Matchup Cells

| Direction | Cell | Count | Adj 4x Lift | Avg Pts | Avg Value |
|---|---|---:|---:|---:|---:|
| Positive | RB:BUF_vs_NYJ | 16 | 7.25pp | 5.66 | 1.18x |
| Positive | WR:IND_vs_PIT | 18 | 6.39pp | 3.61 | 0.81x |
| Positive | WR:DET_vs_JAC | 8 | 6.24pp | 9.74 | 1.59x |
| Positive | WR:CIN_vs_DET | 8 | 6.24pp | 7.05 | 1.27x |
| Positive | WR:NE_vs_NO | 8 | 6.24pp | 6.63 | 1.79x |
| Positive | WR:DEN_vs_DAL | 8 | 6.24pp | 6.42 | 1.57x |
| Positive | WR:CIN_vs_CHI | 8 | 6.24pp | 9.28 | 1.73x |
| Positive | WR:NE_vs_TB | 8 | 6.24pp | 6.85 | 1.80x |
| Positive | WR:NE_vs_HOU | 9 | 5.91pp | 4.49 | 1.20x |
| Positive | WR:DEN_vs_ATL | 9 | 5.91pp | 7.04 | 1.87x |
| Positive | WR:CLE_vs_NO | 9 | 5.91pp | 6.40 | 1.32x |
| Positive | WR:NYG_vs_IND | 9 | 5.91pp | 7.49 | 1.46x |
| Positive | WR:CHI_vs_CIN | 9 | 5.91pp | 4.53 | 1.09x |
| Positive | RB:ATL_vs_CAR | 10 | 5.85pp | 9.12 | 1.43x |
| Positive | WR:TB_vs_MIA | 10 | 5.61pp | 6.92 | 1.55x |
| Negative | QB:CLE_vs_CIN | 16 | -2.71pp | 3.06 | 0.64x |
| Negative | QB:BAL_vs_PIT | 15 | -2.61pp | 4.03 | 0.50x |
| Negative | QB:CIN_vs_CLE | 15 | -2.61pp | 4.61 | 0.66x |
| Negative | QB:ATL_vs_NO | 15 | -2.61pp | 3.23 | 0.61x |
| Negative | QB:IND_vs_TEN | 13 | -2.40pp | 4.55 | 0.78x |
| Negative | QB:NYJ_vs_BUF | 13 | -2.40pp | 3.40 | 0.67x |
| Negative | TE:CIN_vs_CLE | 35 | -2.27pp | 0.87 | 0.26x |
| Negative | TE:NO_vs_ATL | 32 | -2.20pp | 1.79 | 0.50x |
| Negative | QB:TEN_vs_JAC | 11 | -2.16pp | 2.77 | 0.58x |
| Negative | QB:CIN_vs_PIT | 11 | -2.16pp | 5.92 | 0.69x |
| Negative | QB:NYJ_vs_NE | 11 | -2.16pp | 3.89 | 0.52x |
| Negative | QB:LV_vs_KC | 11 | -2.16pp | 0.69 | 0.16x |
| Negative | WR:ATL_vs_NO | 40 | -2.12pp | 2.43 | 0.44x |
| Negative | TE:MIN_vs_GB | 29 | -2.11pp | 1.48 | 0.46x |
| Negative | WR:BAL_vs_PIT | 39 | -2.10pp | 1.75 | 0.36x |

## Position Baselines

| Position | Count | Avg Pts | Avg Value | 3x Hit | 4x Hit |
|---|---:|---:|---:|---:|---:|
| DST | 656 | 5.71 | 1.83x | 21.2% | 11.7% |
| QB | 2313 | 5.12 | 0.83x | 12.2% | 6.1% |
| RB | 3881 | 3.61 | 0.63x | 5.7% | 2.4% |
| TE | 3810 | 2.27 | 0.66x | 7.3% | 3.6% |
| WR | 6682 | 3.12 | 0.64x | 6.3% | 3.2% |

