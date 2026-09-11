# Projection Model V3 Evaluation

Date: 2026-09-07

## Outcome

The `gradient_boosting_active_v3_position_role` challenger passed the declared
overall validation and chronological test MAE gates against the prior canonical
projection algorithm. It also improved the $6,000-plus salary cohort in both
windows and improved the test MAE for each supported position: QB, RB, WR, TE,
and DST.

The challenger projection run is
`3868cdda-7380-4e99-83a9-80f14894b5b0`. The prior active run is
`4c2f69d0-16ad-4e44-8aa0-61a71767ecfe`.

The passed evaluation is `model-evaluation:75e1491740cee354cd814ed3`.
Named promotion decision `model-decision:7ed4f931db3d076584b3ff80` selected
the challenger and preserves the prior run as its exact rollback target.

## Contracts Compared

Champion:

- all supported positions fit together without an explicit position input;
- all historical salary-pool rows remain in training;
- point estimate is 60% raw gradient boosting plus 40% of the 3.78-point
  all-position training mean;
- receiver role inputs are unavailable in the canonical matrix.

Challenger:

- requires `played_confirmed` or `played_inferred` evidence for historical
  QB/RB/WR/TE labels and retains DST rows separately;
- preserves zero-point labels when the player actually participated;
- adds explicit QB/RB/WR/TE/DST model indicators;
- point estimate is 80% raw model plus 20% of the strictly prior 60/40
  roll-three/roll-eight player-history anchor, with a position-mean fallback
  below three games;
- derives receiver roles from a strictly lagged three-game offensive snap share;
- uses the same `GradientBoostingRegressor(random_state=42)` family.

## Time Windows

| Window | Start | End |
| --- | --- | --- |
| Training | 2014 Week 1 | 2024 Week 18 |
| Validation | 2025 Week 1 | 2025 Week 9 |
| Chronological test | 2025 Week 10 | 2025 Week 18 |

The validation and test cohorts contain only rows accepted by the challenger's
historical participation contract so both algorithms are compared on the same
player-games.

## Aggregate Evidence

| Cohort | Rows | Validation champion | Validation challenger | Test rows | Test champion | Test challenger |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All accepted players | 1,979 | 4.4805 | 4.3533 | 2,106 | 4.2877 | 4.1530 |
| Salary $6,000+ | 289 | 7.6341 | 6.8026 | 309 | 7.2988 | 6.6525 |

## Position Test Evidence

| Position | Rows | Champion MAE | Challenger MAE | Improvement |
| --- | ---: | ---: | ---: | ---: |
| QB | 198 | 7.4443 | 6.6615 | 0.7828 |
| RB | 515 | 4.2253 | 4.1886 | 0.0366 |
| WR | 751 | 4.2907 | 4.2878 | 0.0029 |
| TE | 488 | 3.1122 | 2.9542 | 0.1581 |
| DST | 154 | 4.1483 | 3.9846 | 0.1637 |

## Known Tradeoffs

The validation-window RB and WR MAEs regress by 0.0899 and 0.0466 points,
respectively. The later chronological test reverses both regressions, but the WR
test lift is small. This change therefore fixes the severe inactive-row/global-
mean bias and improves aggregate/high-salary accuracy; it does not claim that
the current feature family has solved opportunity and efficiency modeling.
Target share, routes, and carry share remain appropriate future candidates when
canonical point-in-time sources are populated.

## Current-Slate Check

The repaired immutable 2026 Week 1 `WEDNESDAY_NIGHT` run contains 63 players.
Jaxon Smith-Njigba is classified `PRIMARY` from an 89.3% lagged three-game snap
share and projects at 14.33 mean / 25.43 P90, versus 9.44 / 15.41 under the prior
run. The filter reduces the model training set from 15,968 to 8,594 rows and the
zero-label rate from 59.3% to 26.2% without removing confirmed zero-point
appearances.
