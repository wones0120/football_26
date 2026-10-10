# Current Classic GPP ranking audit and first challenger

Decision: **retain the current live recommendation**. Reject the first fixed
mean-guarded upside challenger for deployment. The shadow was tested without
changing optimizer settings, live recommendations or projection values.

## What actually runs

1. Player eligibility and preliminary ranking: `classic_candidate_policy.py`
   defines context-adjusted marginal P90/value thresholds, positional limits
   (QB 14, RB 20, WR 34, TE 16, DST 12), team caps and stack-safety addbacks.
   This is a player-pool narrowing step, not a broad lineup shortlist. User
   exclusions remain optimizer preferences rather than projection changes.
2. Lineup generation: `build_large_gpp_config` and `_build_lineup` use a normalized
   objective with mean .35, ceiling .45, leverage .05 and correlation .15 when
   ownership is available. Context adjustments and fixed normalization denominators
   participate in the effective objective; these weights are not calibrated
   probabilities. Ownership fallback uses .35/.48/0/.17.
3. Sequential selection: each accepted ILP solve consumes exposure budgets, changes
   overlap/exclusion constraints and advances the compatible stack-template cycle.
   Accepted lineups are the returned candidates. The current large-GPP path does
   **not** generate the legacy small-field path's hundreds of lineups and then
   shortlist them. Sequential optimal solves do not establish joint portfolio
   optimality or the globally best one-lineup recommendation.
4. Final recommendation: `gpp_recommendation.evaluate_candidates` validates exports
   and canonical identities, then maximizes baseline projected-point sum. Summed
   player P90 breaks exact ties, then canonical identity. It compares only returned
   candidates; there is no calibrated opponent-field paid-finish objective.

The latest saved Sunday Main run `eb324261-7630-492a-ad78-cad5f72bb43b` confirms
these effective ownership-available weights, team cap 2, game cap 3, overlap 5,
and stack templates (1 teammate, no bring-back) / (1 teammate, 1 bring-back).
The effective strategy contract and solver-step/portfolio audit already preserve
important trace evidence. No new logging hook or live mutation was necessary.

## Architecture findings

- Generation and recommendation optimize different metrics. A projection-first
  recommendation cannot recover a high-mean lineup that the ceiling/correlation-led
  sequential generator never returned. This is a hypothesis to test, not proof of
  a current generation error.
- Exposure and overlap are portfolio controls. Their order-dependent effects also
  influence the candidates available when the user's intent is to play one lineup.
  Keep existing controls; isolate their effects in a future paired experiment.
- Legacy small-field shortlisting failures do not establish a corresponding current
  large-GPP shortlist bug. The two paths must remain separate in evaluation.
- Historical current-strategy evidence is sparse: 35 saved runs inspected, 14 eligible
  historical runs across only Weeks 3 and 4; other runs are unavailable or pending.

## Fixed challenger and result

[Protocol](classic_gpp_shadow_protocol.md): retain at least 98% of the highest
projected total, then choose the highest summed marginal player P90. The fixed
2% band was specified before joining outcomes and was not tuned afterward.
It is an uncalibrated ranking hypothesis, not a lineup percentile or paid probability.

Primary cases use the most recent eligible run per slate, selected by time rather
than outcome:

| Sunday Main | Current-policy replay | Challenger | Paid GPPs: current → challenger |
|---|---:|---:|---:|
| Week 3 | 146.90 | 104.94 | 2/3 → 0/3 |
| Week 4 | 153.90 | 116.88 | 3/3 → 0/3 |

The Week 3 change sacrificed 1.81 projected points for just 0.51 additional summed
P90. Week 4 sacrificed 0.25 projected points for 2.73 additional summed P90. Actual
results deteriorated substantially. This does not prove that marginal upside is
always harmful; it provides no evidence to deploy this particular tradeoff.

Sensitivity over all 14 eligible historical runs: five changed choices, each worse
in actual points and paid-finish comparisons; nine identical choices. Repeated runs
and contests are dependent observations. Neither policy achieved a top-1% finish in
the primary comparisons. Exact challenger earnings and expected return remain
unavailable without payout ladders. These previously inspected slates are not an
untouched validation set; no fitted weights or promotion claims are made.

## Upcoming Sunday Main and next step

Eight existing upcoming runs received separately saved prelock shadow comparisons.
In the latest run both policies choose **lineup #2**, projected 133.07 with a 232.96
sum of player P90s. That P90 sum is not a joint lineup percentile. Outcomes are
pending. Forecast-only choices were frozen before any result loading, and the JSON
retains hashes, timestamps, scope, effective configuration and upcoming candidate
rosters. It is a local research snapshot, not independently timestamped immutable
storage. No automatic future settlement or live policy routing was added.

Next recommended experiment: isolate the sequential generator's scoring and
portfolio-order effects using frozen inputs and identical user constraints,
followed by the unchanged projection-first selector. This tests whether it can
supply better paid-finish candidates, rather than abandoning projected points for
small uncalibrated upside gains. Do not tune another ranker against these same two
weeks. Preserve upcoming outcomes as prospective evidence before promotion.

## Reproduce and validation

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_classic_gpp_shadow.py \
  --output-dir artifacts/classic_gpp_shadow/new-run
```

The script refuses to overwrite a prior report JSON. Its database transaction is
read-only. Production code does not import the shadow module. Forecast choices,
policy and inputs are hashed; missing upside makes the challenger unavailable.
See `artifacts/classic_gpp_shadow/report.md` and `report.json` for results.

Acceptance: 44 targeted challenger/recommendation/historical-audit tests passed.
Python compilation and documentation whitespace checks passed. A post-experiment
readback confirmed that all 35 saved recommendation hashes and effective-strategy
contract hashes remained unchanged. No API restart or worker activation was needed.
