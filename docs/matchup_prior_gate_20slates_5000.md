# Matchup Prior Gate

- Source diagnostics: `/Users/wones/git/football_26/docs/matchup_prior_help_diagnostics_20slates_5000.json`  Base prior strength: `0.15`
- Selected threshold: `12.0`  Rules: `9`

## Threshold Evaluation

| Threshold | Active Slates | Active Rate | Gated Mean Gap | Lift vs Baseline | Lift vs Always On | Win Rate |
|---:|---:|---:|---:|---:|---:|---:|
| -12.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| -8.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| -4.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| 0.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| 2.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| 4.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| 6.00 | 18 | 100.0% | 120.998 | 4.650 | 0.000 | 33.3% |
| 8.00 | 17 | 94.4% | 120.392 | 5.256 | 0.606 | 33.3% |
| 10.00 | 17 | 94.4% | 120.392 | 5.256 | 0.606 | 33.3% |
| 12.00 | 16 | 88.9% | 120.392 | 5.256 | 0.606 | 33.3% |

## Rules

| Bucket | Value | Weight | Support | Help Rate | Hurt Rate |
|---|---|---:|---:|---:|---:|
| max_total_bucket | shootout_total | 19.253 | 6 | 50.0% | 0.0% |
| low_salary_skill_share_bucket | low_salary_skill_high | 8.113 | 6 | 66.7% | 16.7% |
| max_implied_bucket | elite_implied | 6.757 | 14 | 42.9% | 14.3% |
| favorite_skill_share_bucket | favorite_skill_medium | 5.231 | 16 | 37.5% | 18.8% |
| high_total_skill_share_bucket | high_total_skill_low | 4.959 | 16 | 31.2% | 18.8% |
| low_salary_skill_share_bucket | low_salary_skill_very_high | 2.918 | 12 | 16.7% | 16.7% |
| close_spread_share_bucket | close_spread_low | 2.120 | 12 | 33.3% | 8.3% |
| max_implied_bucket | high_implied | -2.725 | 4 | 0.0% | 25.0% |
| max_total_bucket | high_total | -3.536 | 9 | 33.3% | 33.3% |

## Selected Gate Rows

| Season | Week | Slate | Active | Score | Baseline Gap | Always-On Gap | Gated Gap |
|---:|---:|---|---|---:|---:|---:|---:|
| 2024 | 6 | main | yes | 46.434 | 147.100 | 147.100 | 147.100 |
| 2024 | 9 | main | yes | 44.314 | 185.520 | 124.320 | 124.320 |
| 2024 | 7 | 1pm_slate | yes | 41.475 | 141.720 | 137.360 | 137.360 |
| 2024 | 15 | sunday_all | yes | 39.119 | 210.820 | 160.860 | 160.860 |
| 2024 | 7 | monday_night | yes | 34.160 | 68.700 | 68.700 | 68.700 |
| 2024 | 15 | sunday_late | yes | 31.757 | 116.000 | 116.000 | 116.000 |
| 2024 | 8 | normal | yes | 23.645 | 168.240 | 149.540 | 149.540 |
| 2024 | 10 | sunday | yes | 23.645 | 104.640 | 98.220 | 98.220 |
| 2024 | 15 | sunday_early | yes | 21.985 | 176.800 | 176.800 | 176.800 |
| 2024 | 11 | main | yes | 21.525 | 162.120 | 204.120 | 204.120 |
| 2024 | 12 | main | yes | 18.450 | 165.420 | 163.380 | 163.380 |
| 2024 | 16 | main | yes | 18.450 | 188.860 | 194.940 | 194.940 |
| 2024 | 16 | monday_night_unknown | yes | 18.450 | 77.340 | 77.340 | 77.340 |
| 2024 | 13 | thursday | yes | 13.219 | 32.900 | 32.900 | 32.900 |
| 2024 | 15 | monday_classic | yes | 12.503 | 9.980 | 9.980 | 9.980 |
| 2024 | 16 | saturday | yes | 12.503 | 70.720 | 70.720 | 70.720 |
| 2024 | 16 | afternoon_only | no | 11.099 | 101.900 | 101.900 | 101.900 |
| 2024 | 13 | main | no | 6.848 | 132.880 | 143.780 | 132.880 |

