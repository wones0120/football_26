# Online Weekly Residual Learning

- Slice: `draftkings 2024-2025 sunday_main`
- Historical observations: `3342` across `15` completed slates.
- Selected shrinkage strength: `5.0` using validation MAE only.
- Candidate status: `promotion candidate for broader integration`.
- Production model changed: `no`.

## Untouched Test Result

| Metric | Baseline | Residual-adjusted | Lift / Change |
|---|---:|---:|---:|
| MAE | 4.818 | 4.602 | +4.48% |
| RMSE | 6.551 | 6.389 | +2.47% |
| Mean error | +0.613 | +0.282 | -0.331 |

## Validation-Only Strength Selection

| Prior strength | Validation adjusted MAE | Validation lift | Test adjusted MAE | Test lift |
|---:|---:|---:|---:|---:|
| 5.0 | 4.866 | +4.88% | 4.602 | +4.48% |
| 10.0 | 4.879 | +4.63% | 4.613 | +4.26% |
| 20.0 | 4.894 | +4.33% | 4.625 | +4.01% |
| 40.0 | 4.912 | +3.98% | 4.637 | +3.75% |
| 80.0 | 4.930 | +3.62% | 4.650 | +3.49% |

## Test Result by Position

| Position | Rows | Baseline MAE | Adjusted MAE | Lift | Mean error before | Mean error after |
|---|---:|---:|---:|---:|---:|---:|
| QB | 138 | 7.352 | 6.904 | +6.09% | +2.405 | +1.644 |
| RB | 315 | 4.784 | 4.509 | +5.74% | +0.095 | -0.502 |
| TE | 266 | 3.499 | 3.474 | +0.70% | -0.134 | +0.178 |
| WR | 486 | 4.842 | 4.626 | +4.47% | +0.849 | +0.462 |

## Walk-Forward Slices

| Slice | Window | Rows | Baseline MAE | Adjusted MAE | Lift | Mean absolute adjustment |
|---|---|---:|---:|---:|---:|---:|
| 2025-W05 | validation | 230 | 5.163 | 4.934 | +4.43% | 1.032 |
| 2025-W06 | validation | 220 | 4.859 | 4.568 | +5.99% | 0.699 |
| 2025-W07 | validation | 230 | 5.143 | 4.912 | +4.49% | 0.734 |
| 2025-W08 | validation | 226 | 5.097 | 4.797 | +5.90% | 0.783 |
| 2025-W09 | validation | 250 | 5.236 | 4.979 | +4.91% | 0.670 |
| 2025-W10 | validation | 222 | 5.174 | 4.985 | +3.65% | 0.671 |
| 2025-W11 | test | 251 | 5.198 | 5.018 | +3.46% | 0.692 |
| 2025-W12 | test | 245 | 4.998 | 4.778 | +4.39% | 0.661 |
| 2025-W13 | test | 219 | 4.611 | 4.338 | +5.92% | 0.657 |
| 2025-W17 | test | 202 | 4.651 | 4.460 | +4.09% | 0.664 |
| 2025-W18 | test | 288 | 4.608 | 4.391 | +4.72% | 0.719 |

## Time-Safety and Scope

- Validation: `2025-W05` through `2025-W10`.
- Untouched test: `2025-W11` through `2025-W18`.
- Rolling history window: `12` completed week slices.
- Maximum absolute adjustment: `6.0` points.
- Inputs: canonical player identity, team-position, opponent-position, salary bucket, projected-value bucket, and pre-lock total/spread regime.
- Every target week is scored only from residuals belonging to strictly earlier week slices. Raw display names are never used as identity keys.
