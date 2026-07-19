# Future-Safe Game-Regime Projection Ensemble

- Rows: `17342` across `28` week slices
- Selected minimum cell rows: `300`
- Selected prior strength: `1000.0`
- Candidate status: `research_not_promoted`
- Production model changed: `no`
- Canonical identity coverage: `79.7%`
- Known pregame regime coverage: `100.0%`

## Validation-Selected Candidate

| Window | Global MAE | Ensemble MAE | MAE lift | Specialist coverage |
|---|---:|---:|---:|---:|
| validation | 2.791 | 2.798 | -0.27% | 67.9% |
| untouched test | 2.573 | 2.574 | -0.04% | 71.8% |

## Untouched Test by Position

| Position | Rows | Global MAE | Ensemble MAE | Lift |
|---|---:|---:|---:|---:|
| DST | 104 | 4.061 | 4.061 | +0.00% |
| QB | 374 | 3.423 | 3.441 | -0.53% |
| RB | 621 | 2.613 | 2.628 | -0.56% |
| TE | 602 | 1.811 | 1.821 | -0.55% |
| WR | 1033 | 2.534 | 2.516 | +0.73% |

## Untouched Test by Week

| Slice | Rows | Global MAE | Ensemble MAE | Lift |
|---|---:|---:|---:|---:|
| 2025-W12 | 616 | 2.599 | 2.607 | -0.31% |
| 2025-W13 | 666 | 2.343 | 2.334 | +0.36% |
| 2025-W16 | 61 | 2.681 | 2.709 | -1.02% |
| 2025-W17 | 714 | 2.595 | 2.574 | +0.80% |
| 2025-W18 | 677 | 2.741 | 2.766 | -0.89% |

## Safety

- Total and spread are pregame schedule inputs.
- Every validation/test prediction is trained only on earlier whole-week slices.
- Unknown and sparse regime-position cells use the global tree exactly.
- Blend parameters are selected on validation; the test window is not used for selection.
- Position/regime test improvements are not promoted when the same subset did not improve validation.
- The result is research-only and does not change production automatically.
