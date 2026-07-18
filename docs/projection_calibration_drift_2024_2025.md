# Player Projection Calibration Drift

- Evaluated slates: `15` / `15`
- Evaluated players: `2856`
- Simulation iterations per slate: `1000`
- Alerts: `0`

## Overall Calibration

| Metric | Predicted / Expected | Observed | Error |
|---|---:|---:|---:|
| P75 coverage | 75.0% | 76.4% | +1.4% |
| P90 coverage | 90.0% | 90.3% | +0.3% |
| P95 coverage | 95.0% | 94.7% | -0.3% |
| 25+ point tail probability | 5.7% | 5.5% | +0.2% |

## Window Drift

| Metric | Early | Late | Delta |
|---|---:|---:|---:|
| P75 coverage | 75.6% | 77.1% | +1.5% |
| P90 coverage | 90.0% | 90.5% | +0.5% |
| P95 coverage | 94.9% | 94.6% | -0.3% |
| Mean prediction error | +0.28 | +0.33 | +0.05 |

## Alerts

- None at the configured sample and drift thresholds.

All simulation calibration lookups are point-in-time safe: only factors from weeks before the evaluated target are eligible. The report is observational and does not mutate stored factors.
