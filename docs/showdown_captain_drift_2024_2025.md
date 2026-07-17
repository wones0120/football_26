# Showdown Captain Prior Drift

- Alert threshold (total variation): `0.250`
- Minimum slates per segment: `5`
- Alerts: `1`

## Segment Priors

| Segment | Slates | QB | RB | WR | TE | K | DST |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024_mid | 6 | 0.0% | 16.7% | 83.3% | 0.0% | 0.0% | 0.0% |
| 2024_late | 17 | 17.6% | 23.5% | 35.3% | 17.6% | 0.0% | 5.9% |
| 2025_early | 4 | 50.0% | 25.0% | 25.0% | 0.0% | 0.0% | 0.0% |
| 2025_mid | 10 | 40.0% | 20.0% | 30.0% | 10.0% | 0.0% | 0.0% |
| 2025_late | 4 | 25.0% | 25.0% | 50.0% | 0.0% | 0.0% | 0.0% |

## Consecutive Segment Drift

| From | To | TV Distance | Largest Shift | Alert |
|---|---|---:|---|---|
| 2024_mid | 2024_late | 0.480 | WR | YES |
| 2024_late | 2025_early | 0.338 | QB | no |
| 2025_early | 2025_mid | 0.150 | TE | no |
| 2025_mid | 2025_late | 0.250 | WR | no |

Total variation measures how much captain-position probability mass moved between segments. Alerts require both segments to meet the minimum sample size.
