# Late-2025 Point-in-Time Shock Validation

## Verdict

Accepted for projection-scenario research. Three late-2025 DraftKings slices
completed without warnings, targeted only the requested teams and positions,
preserved nonnegative outcomes, and reproduced the requested post-floor mean
multipliers to floating-point precision.

These are synthetic stress tests. They do not claim that the stored schedule
weather was a timestamped pre-lock observation, that the news event occurred,
or that the supplied multipliers estimate causal historical effects.

## Coverage

| Slice | Salary rows | Mapped | Mapping |
| --- | ---: | ---: | ---: |
| 2025 W16 Monday night | 112 | 108 | 96.4% |
| 2025 W17 Sunday main | 470 | 459 | 97.7% |
| 2025 W18 Sunday main | 677 | 663 | 97.9% |

## Accepted Replays

| Slice / scenario | Run ID | Affected rows / players | Mean × | Aggregate mean Δ | P90 increased | Warnings |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| W16 SF–IND synthetic SF news downgrade | `9e5d9fbc-a602-41d6-9409-0caa640104df` | 50 / 25 | 0.9200000000000003 | -30.92 | 34 | 0 |
| W17 PIT–CLE synthetic wind stress | `6de45d0b-9ff6-4825-af3e-af7e0f0a85ab` | 37 / 37 | 0.92 | -19.41 | 30 | 0 |
| W18 NYJ–BUF synthetic cold/wind stress | `1b07d76d-fc20-4bf3-96c5-d1ade7d80346` | 34 / 34 | 0.9000000000000002 | -23.99 | 27 | 0 |

All runs used 5,000 iterations and seed `42`. The W17 request was repeated as
run `632fa1c8-a9b5-4299-9e72-56670d33a542`; after excluding run identity and
timestamps, both responses had SHA-256
`e6f8400b44ba4e62b686d7cbb301d099e26626fc604ff633b34c72692698ce92`.

P90 increases are expected in many rows because the scenarios deliberately
combine a lower mean with wider volatility. The mean and tail assumptions are
separate controls.

## Defect Found and Corrected

The first replay pass exposed a zero-floor edge case. Widening deviations and
then clipping negative draws to zero could make a low-projection player’s
realized mean increase even when `mean_multiplier < 1`.

The transform now solves for the pre-floor location that produces the requested
post-floor mean. Focused tests cover a zero-heavy distribution. In all corrected
historical replays:

- positive mean deltas: `0`;
- unexpected team/position targets: `0`;
- minimum scenario mean: greater than `0`;
- maximum per-player multiplier error: `2.22e-16`; and
- scenario warnings: `0`.

The superseded, traceable runs are:

- W16: `75a75650-be14-4265-9e2e-8449353ec098`;
- W17: `bc9b8189-4d87-476b-88f1-981e11cb5639`; and
- W18: `a24c4614-546c-448c-9107-999ada867d63`.

## Acceptance Boundary

This evidence accepts the projection-distribution shock path. Ultimate lineup
generation currently computes its own projections and does not consume a
selected `simulation_run`. Therefore this report does not claim lineup
portfolio sensitivity or scenario reoptimization value.

The next implementation step is an explicit, slice-validated
`simulation_run_id` projection override for lineup generation, followed by
matched baseline-versus-shock lineup comparison.

Machine-readable evidence:
`docs/point_in_time_shock_validation_2025_late_season.json`.
