# Captain ceiling and conditional FLEX research

This is an offline selection comparison. It has no API/UI integration, changes no
production defaults, and never alters projections, ownership, availability or
user preferences. Implementation: `captain_flex_research.py` in product services;
runner: `scripts/research_captain_flex.py`.

## What “FLEX benefits from captain success” means

Ask: **if this captain has a big game, how does that change the outlook for each
FLEX player?** This is a conditional association, not a claim that the captain
causes another player's score. Both may benefit from the same game conditions.
Not every FLEX player needs positive support: a strong individual forecast can
still justify a player whose outcome is independent or slightly conflicting.

| Captain's success route | Potential FLEX support | Potential conflict |
|---|---|---|
| Receiver produces heavily | His QB shares passing yards and touchdowns | Teammate receivers compete for finite targets/TDs; opposing DST suffers |
| Pocket QB has a big passing game | Same-team receivers share the passing environment | Opposing DST; highly concentrated receiving production may make a receiver the better captain |
| Rushing QB has a big game | Much weaker direct benefit to receivers | Same-team RB competes for rushing opportunity |
| Early-down RB succeeds | Own DST can share a favorable game script | Other rushing players compete; passing production need not rise |
| Receiving RB succeeds | Own QB shares receiving production | Other receivers compete for opportunity |

These are hypotheses implemented with explicit statistical priors. There is no
hard receiver/QB stacking requirement added by this experiment. It does **not**
simulate individual plays, conserve actual team targets/TDs, or require the
captain to outscore every other player. In particular, QB distribution across
multiple receivers is approximated by common passing factors and competition;
it is not a calibrated “QB is optimal captain” event.

## The actual calculation

Every player retains the frozen base-slot mean `mu` and P90. For the research
proxy only, approximate a normal spread:

```
z90 = 1.2815515655
sigma = (P90 - mu) / z90
lambda90 = normal_density(z90) / 0.10 = 1.7549833193
captain_upper_tail_mean = mu_C + sigma_C * lambda90
FLEX_lift_i = correlation_proxy(C, i) * sigma_i * lambda90

ceiling_only = 1.5 * captain_upper_tail_mean + sum(FLEX means)
captain_flex = ceiling_only + sum(FLEX_lift_i)
```

This is the analytic expected lineup score **conditional on the captain reaching
his own P90**, under the assumed Gaussian dependence model. It combines absolute
captain scoring potential and compatible FLEX scoring. It is **not** a lineup
P90, cash probability, win probability, or payout expectation. Conditioning on
each captain's own P90 also gives each nondegenerate captain a nominal 10% tail;
that is not evidence that their chances of winning are equal.

The 1.5 multiplier applies once to the captain only. A zero-spread captain gets
no conditional FLEX lift and is labeled degenerate. Invalid/nonfinite forecasts
or P90 below mean fail explicitly. Signed conditional estimates are retained;
this approximation can produce physically unrealistic tails or negative skill
player estimates. That is a model limitation, not a new football projection.

For example, a receiver captain can contribute 45 conditional captain points,
while the five FLEX means total 60 and their conditional shifts sum to +4. The
combined proxy is 109. Those four extra proxy points must be traced to supporting
relationships; they are not added to any saved player projection.

## How the relationships are encoded

Each player's standardized outcome has shared factor loadings and independent
residual variance. Correlation is the dot product of two players' shared
loadings. Residual variance makes the resulting covariance matrix valid.

| Shared factor | Fixed v1 loading |
|---|---|
| Game scoring environment | +0.20 offense/kicker; -0.20 DST |
| Own-team passing | QB: `0.60 * (1 - rushing_role)`; WR/TE: 0.35; RB: `0.35 * receiving_role` |
| Team lead/trail script | Passing positions: 0.15 toward trailing, reduced for rushing QBs; RB: 0.30 toward leading times rushing role; DST: 0.30 toward leading |
| Opponent passing versus DST | DST: -0.40 on the opponent's passing factor |
| Receiving opportunity competition | Opposite signs for teammate pairs, scale 0.60, weighted by receiving role |
| Rushing opportunity competition | Opposite signs for QB/RB teammate pairs, scale 0.35, weighted by rushing role |

Competition loadings divide by `sqrt(group_size - 1)`, keeping variance bounded.
Groups use the fixed players represented in the frozen candidate archive, not
only players selected in a particular lineup. Consequently results depend on
archive coverage; expanding that archive can change the competition model.
Common game/passing effects can outweigh competition, so two teammate receivers
may still have positive net support. The JSON preserves each signed contribution.

Roles use saved expected carries/targets, then saved projected opportunity,
then lagged three-game opportunity. QB rushing role is `min(1, carries / 6)`;
RB receiving role is `targets / (targets + 0.25 * carries)`, and its rushing role
is one minus that fraction. These are declared research assumptions, not fitted
football estimates. Missing role evidence is explicitly labeled and uses 0.5;
sensitivity arms use 0 and 1. Zero known QB carries is valid evidence, not missing.
Player names never determine identity or archetype.

## Comparison controls and safeguards

- **Saved selector:** existing selector scores on the common frozen candidate set.
- **Ceiling only:** conditional captain contribution plus ordinary FLEX means.
- **Captain + FLEX:** the same score with signed conditional FLEX shifts.
- Sensitivities: half dependence, unknown roles at 0/1, and no competition.

The second and third arms replace the ranking objective; they do not stack this
bonus on top of existing correlation/position-prior bonuses. Their direct
comparison isolates the conditional FLEX term. Mean/P90 quality gates, requested
count, recorded exposure caps, candidate rosters and salaries remain fixed.
The runner reuses the existing portfolio selector and validates reconstructed
canonical IDs, CPT/FLEX weighting, both teams and salary legality. No new
candidates or submission files are generated. Preferences embodied in these
old candidate sets are historical; current browser preferences are not applied.

The manifest fixes source files, scope, native kickoff and v3 exposure rates for
classes absent from a saved selected roster. Source envelopes and universe/pool
hashes are verified; output retains source hashes, compact replay inputs, policy
code hashes, Python/PuLP versions and the CBC binary hash. Repeated identical
runs reuse the same immutable content-addressed output.

Selection for every slate finishes before actual-score files are read. Actual
labels join by canonical ID in an explicitly checked season/week/slate, and
captain actuals are converted to base points exactly once. Conflicting or missing
scores stay unavailable; they are never imputed as zero. No priors were fitted
to these outcomes. The policy itself was designed retrospectively, so this is
not a prospective holdout test.

Recorded job and forecast clocks are compared with the frozen native kickoff;
filesystem modification time is not treated as historical evidence. These
checks do not independently certify every upstream observation's availability.

## Frozen results

Full [comparison report](../../artifacts/captain_flex_research/32b7b64c11d8f28218749cfd7e736144a346a3a4c6731df27bafe47aadc05807.md)
and [replay/evidence JSON](../../artifacts/captain_flex_research/32b7b64c11d8f28218749cfd7e736144a346a3a4c6731df27bafe47aadc05807.json).

| Slate | Physical candidates | Selected count | Saved-selector actual mean | Ceiling-only actual mean | Combined actual mean | Saved / combined best actual |
|---|---:|---:|---:|---:|---:|---:|
| 2026 W4 Thursday PIT-CLE | 533 | 4 of 5 | 92.38 | 93.28 | 92.38 | 99.77 / 99.77 |
| 2026 W4 Monday ATL-NO | 115 | 5 of 5 | 96.18 | 96.18 | 97.97 | 109.21 / 109.21 |
| 2026 W4 Sunday DET-CAR, retrospective only | 110 | 5 of 5 | 108.40 | 107.28 | 107.72 | 111.37 / 111.78 |

All candidate actual labels are complete in the final run. Monday's full labels
were captured from existing resolved contest observations using a read-only
database transaction, after the initial selections were saved. That immutable
capture includes the initial selection artifact hash. Replays use only files.

Thursday's archive combines production and research candidates: its saved-score
control is a common-universe replay, **not** a reproduction of the original
production portfolio. Monday and Sunday saved-selector controls reproduce their
original physical portfolios. The retained gates/caps underfill Thursday in all
arms; the experiment does not relax them to manufacture a fifth lineup.

On Monday the combined method replaced an Olave-CPT lineup scoring 92.54 with a
Shough-CPT lineup scoring 101.51. The latter paired Shough with Olave, Juwan
Johnson and Devaughn Vele, plus Charlie Smyth and Brian Robinson Jr. The captain
upper-tail contributions were similar (53.74 versus 53.98), while conditional
FLEX support rose from 5.66 to 7.49. Those are proxy components, not measured
probabilities. Best selected score and retained-candidate regret did not improve.

Sunday's job was created after kickoff and is excluded from pregame outcome
conclusions. It remains useful for checking the research machinery. Six QB/RB
roles are unknown in each Monday/Sunday snapshot. Monday changes one selection
under half dependence, one under the high unknown-role assumption, and two when
competition is removed. That sensitivity is material.

**Keep defaults unchanged.** Two pregame-clock-eligible slates do not establish
an advantage; Thursday did not improve, Monday improved average score only, and
results depend on unvalidated assumptions. Regret here refers only to retained
candidates, not all legal rosters. There is no payout, duplication, field-rank,
calibrated bust-risk or tournament-win improvement claim.

Next evidence needed: a larger prospective archive with complete point-in-time
role forecasts, validation of the conditional dependence model, and eventually
joint field outcomes for payout/duplication analysis. Lock assumptions before
evaluating that archive; do not tune the priors on these three slates.

## Reproduce and validate

```sh
.venv/bin/python -m scripts.research_captain_flex
.venv/bin/python -m pytest backend/app/tests/product/test_captain_flex_research.py \
  backend/app/tests/product/test_showdown_portfolio_selection.py \
  backend/app/tests/product/test_showdown_soft_scenarios.py -q
```

The default manifest is `docs/research/captain_flex_manifest.json`. Alternative
frozen cohorts can be supplied with `--manifest PATH`; `--output PATH` changes
the artifact destination. Missing inputs fail explicitly. This runner neither
connects to the database nor imports the live optimizer service.

Validation: 34 targeted tests passed, including seeded Monte Carlo verification
of the analytic formula, rushing/passing role differences, negative competition,
unchanged forecasts, quality/exposure constraints, identity errors, source
checksum failures, outcome-blind ranking and missing/conflicting actual labels.
