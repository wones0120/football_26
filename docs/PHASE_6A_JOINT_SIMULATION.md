# Phase 6A — Experimental joint lineup simulation

Phase 6A's experimental foundation is implemented. SIM-001 remains Research:
learned correlations and out-of-sample calibration are not complete. The new
`joint_game_factor_research_v1` path is accessed through API/CLI; production
simulation selection, optimizer objectives, and model promotion are unchanged.
There is no new UI control in this increment.

## Audit findings

The local audit found 4,506 saved player-simulation rows; 2,253 contain both
replayable distributions and game identity. The inspected recent historical
simulation runs have no `data_cutoff_at`. The current simulation loader selects
latest salary/ownership rows, so a cutoff field alone would not establish
source-observation safety. Phase 6A reads only frozen simulation-run inputs,
never that live loader.

The 2025 Week 11 snapshot contains 382 players across 11 games. Fifteen DST
rows have negative quantiles. These are legitimate signed outcomes, not missing
values. The old independent sampler clips negatives to zero; this experiment
uses a separately versioned signed marginal contract for both its independent
and joint comparisons. It does not rewrite saved or production simulations.

The three newly imported contest exports provide results and ownership evidence,
but ownership rows still lack canonical player mapping and cannot train the
correlation model as-is. No post-contest actuals enter the sampler.

## Sampling contract

Inputs require unique canonical player IDs, explicit canonical game/team/opponent
IDs with consistent two-team games, natural positions, and finite monotone
P10/P25/median/P75/P90 values. Missing identity or invalid distributions fail
explicitly. Ordering is canonical-player-ID stable.

`signed_piecewise_quantiles_research_v1` linearly interpolates quantiles and
extrapolates the outer 10% with finite endpoints. It retains negative values.
The resulting distribution need not have the supplied projection mean, and
its tails are not bounded by a play-level scoring engine. The report exposes
the maximum sampled-mean difference from supplied means. These are research
limitations requiring later calibration, not production-ready distributions.

The joint sampler ranks latent Gaussian draws constructed from shared factors,
then reorders each player's independent values according to those ranks. Thus
independent and joint runs have **exactly the same empirical player marginals**;
only their dependence changes. This does not prove calibration against actuals.

Versioned structural loadings (not learned estimates):

| Factor | Loading |
| --- | --- |
| Game environment | +0.20 offense/kicker; -0.20 DST |
| Same-team passing | +0.50 QB/WR/TE |
| Leading-team script | +0.30 RB/DST |
| Trailing-team script | +0.15 QB/WR/TE |
| Opponent passing effect on DST | -0.40 |

An independent player component supplies the remaining unit variance. Opposite
teams receive opposite script signs. Factors are independent between canonical
games. Configurations with shared variance at or above one fail validation.
These are continuous game-state factors, not estimated categorical game-script
probabilities. Same-team competition and player-role refinements remain future work.

## Lineup comparisons

Supply a completed optimizer run with saved OPT-007 controls and a completed
simulation run with exactly matching season, week, slate, format, projection
run ID, and cutoff. Missing players or controls fail rather than substituting
current projections or inventing distributions.

For each scored/control pair, both lineups use the **same player draws** within
each experimental model. Reports include mean, P10 downside, median, P75, P90,
standard deviation, paired mean difference and its Monte Carlo standard error,
win/tie probability against the control, and optional threshold probability.
These lineup quantiles are calculated from summed outcomes, not summed player
quantiles. Captain receives exactly 1.5 times the player's base outcome.

Thresholds are caller-specified research score thresholds, not claims about
cash lines, top-percentile finishes, opponent fields, payouts, or ROI. Paired
controls are individual alternatives, not a separately validated portfolio.
The evaluator scores existing lineups; it does not construct new ones.

Classic stored snapshots are currently available. The core supports Showdown
slots/K/DST and is tested for Captain scaling, but the existing production
snapshot producer remains Classic-only. A compatible immutable Showdown snapshot
producer is still required for real Showdown comparisons.

## Run and replay

```bash
.venv/bin/python scripts/product/run_joint_simulation_research.py \
  --simulation-run-id SIMULATION_ID \
  --optimizer-run-id OPTIMIZER_ID \
  --num-simulations 5000 --seed 603 --threshold 180
```

Omit the optimizer ID for a snapshot-only sampling smoke check. Missing cutoffs
fail by default. `--allow-missing-cutoff` explicitly enables exploratory-only
historical work, permanently labeled `missing_exploratory_only` in lineage.

`POST /api/simulations/joint-research` accepts the same fields in JSON:
`simulation_run_id`, optional `optimizer_run_id`, `num_simulations`, `seed`,
optional `threshold`, and `allow_missing_cutoff` (default false).
The endpoint returns the report and artifact path, or an actionable 422 error.

Reports are immutable, content-addressed JSON beneath
`artifacts/source_snapshots/joint_simulations/`. They preserve frozen inputs,
lineups, priors, seed, implementation hash, NumPy version, and output draw hash.
Identical inputs reuse the same path without overwriting it. No migration is
needed and no production simulation/champion pointer is changed.

```bash
.venv/bin/python scripts/product/run_joint_simulation_research.py \
  --replay artifacts/source_snapshots/joint_simulations/EXPERIMENT_HASH.json
```

Replay checks source/config/version integrity and recreates outcomes without
database reads. Keep the matching code/dependency version for historical replay.

## Validation and next gate

The real 2025 Week 11 smoke run used simulation
`3a827885-a803-44e0-8c11-0adab090f81c`: 5,000 draws, 382 players, 11 games,
44 shared factors, exact empirical marginal preservation, and reproducible
output hash. It is a snapshot-only smoke test with no historical cutoff and
no optimizer comparison. The saved artifact is
`artifacts/source_snapshots/joint_simulations/3e756bb5d937d974bafaff1eceaacb876ab83ea7ae07330687b082d9b9a46cb6.json`.

Automated tests cover exact marginal preservation, canonical reorder stability,
expected correlation signs, cross-game independence, negative DST outcomes,
invalid inputs, Captain scaling, true lineup quantiles, same-draw paired
comparisons, missing controls, exact lineage/cutoff gating, API behavior,
immutable saves, and replay integrity.

The next research gate is to build a canonical residual dataset with proven
pre-lock projections/source timing, fit correlations on earlier games only,
and reserve later games for teammate/opponent covariance, game-total, marginal,
and lineup-interval calibration checks. Signed-tail behavior and mean/quantile
consistency also need evaluation. Until those gates pass, both
`performance_claim_eligible` and `production_promotion_eligible` remain false.
