# Popularity and Duplication Proxy Validation

- Source: `draftkings`  Seasons: `2024-2025`  Classic slates: `12`
- Candidates requested/slate: `2500`  Generated mean: `687` (range `183-1067`)  Selected/slate: `20`  Seed: `42`

This is a pre-lock popularity proxy, not observed ownership. Historical actual points are used only to measure the cost of diversification after each slate.

## Method

- Player popularity proxy: position-relative salary, projection, ceiling, and value ranks plus implied-total and generated-candidate-exposure ranks.
- Lineup duplication risk: 60% top-five player proxy pressure, 25% generated pair-concentration pressure, and 15% salary-cap usage.
- Penalty: a caller-selected zero-to-one weight applied to standardized proxy risk; zero leaves ranking unchanged.

## Penalty Comparison

| Penalty | Duplication risk | Projected blend | Actual mean | Best actual | Max player exposure |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 0.702 | 126.13 | 91.16 | 137.53 | 55.0% |
| 0.25 | 0.694 | 125.85 | 90.88 | 137.53 | 54.6% |
| 0.50 | 0.678 | 124.09 | 88.88 | 135.69 | 51.7% |
| 0.75 | 0.654 | 119.82 | 82.79 | 128.18 | 49.6% |

## Tradeoffs Versus No Penalty

- Penalty `0.25`: risk `-1.1%`, projection `-0.2%`, actual points `-0.28`.
- Penalty `0.50`: risk `-3.4%`, projection `-1.6%`, actual points `-2.28`.
- Penalty `0.75`: risk `-6.7%`, projection `-5.0%`, actual points `-8.37`.

No penalty is promoted automatically. Use these results to choose an explicit GPP diversification setting and keep the default at zero.
