# MODEL-001 Locked Holdout Evaluation

- Status: `rejected`
- Candidate lock: `73e4597af6352da4893be80355dd714527e1ae5c33c8d7625df0a28d346c4869`
- Candidate MAE: `2.978`
- Baseline MAE: `2.976`
- MAE lift: `-0.04%`
- Production model changed: `no`
- Promotion eligible: `no`

## Position Results

| Position | Selected contract | Rows | Candidate MAE | Baseline MAE | Lift | P10-P90 | P25-P75 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| QB | opportunity_efficiency | 374 | 4.428 | 4.423 | -0.11% | 77.0% | 48.7% |
| RB | history_plus_efficiency | 621 | 2.960 | 2.970 | +0.35% | 80.2% | 48.8% |
| WR | history_plus_efficiency | 1033 | 2.857 | 2.852 | -0.19% | 81.2% | 50.4% |
| TE | opportunity_efficiency | 602 | 2.087 | 2.083 | -0.19% | 79.2% | 50.5% |
| DST | dst_history_baseline | 104 | 4.219 | 4.219 | +0.00% | 77.9% | 49.0% |

## Role Results

| Position | Role | Rows | MAE | RMSE | P10-P90 | P25-P75 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| QB | MOBILE | 67 | 7.921 | 9.570 | 53.7% | 16.4% |
| QB | POCKET | 238 | 4.473 | 6.574 | 77.3% | 46.2% |
| QB | UNKNOWN | 69 | 0.878 | 2.476 | 98.6% | 88.4% |
| RB | COMMITTEE | 366 | 2.480 | 4.265 | 86.3% | 45.1% |
| RB | LEAD | 102 | 7.300 | 9.410 | 40.2% | 10.8% |
| RB | RECEIVING | 18 | 7.306 | 12.450 | 50.0% | 5.6% |
| RB | UNKNOWN | 135 | 0.402 | 1.534 | 97.8% | 93.3% |
| WR | PRIMARY | 122 | 8.245 | 9.864 | 27.9% | 7.4% |
| WR | ROTATION | 469 | 1.820 | 3.102 | 93.4% | 58.4% |
| WR | SECONDARY | 201 | 5.022 | 6.716 | 62.7% | 7.0% |
| WR | UNKNOWN | 241 | 0.343 | 0.919 | 100.0% | 92.9% |
| TE | PRIMARY | 32 | 6.234 | 7.820 | 37.5% | 12.5% |
| TE | ROTATION | 314 | 1.932 | 2.938 | 83.1% | 43.3% |
| TE | SECONDARY | 97 | 4.390 | 5.666 | 47.4% | 8.2% |
| TE | UNKNOWN | 159 | 0.154 | 0.391 | 99.4% | 98.1% |
| DST | DEFENSE | 104 | 4.219 | 5.702 | 77.9% | 49.0% |

## Holdout Gates

- `overall_mae_non_regression`: `fail`
- `dst_mae_non_regression`: `pass`
- `no_position_regresses_more_than_2pct`: `pass`
- `role_metrics_reported`: `pass`

## Promotion Decision

Historical salary membership lacks preserved pre-lock observation timestamps; use a prospectively captured 2026 holdout before promotion.
The evidence may accept or reject the feature decomposition, but it cannot change the active model. A prospective 2026 holdout must pass through MODEL-002 governance.
