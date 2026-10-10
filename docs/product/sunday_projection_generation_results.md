# Sunday Main projection audit and generation shadows — 2026 Week 5

## Decision

Leave the live selector and generator unchanged. Neither of the two predeclared
generation shadows changes the recommended lineup. Improve explicit workload
evidence and validate its effect before further weight tuning. These results are
a frozen-input audit, not a statistical demonstration of improved paid finishes.

Source optimizer run: `eb324261-7630-492a-ad78-cad5f72bb43b`.
Projection run: `506c698c-a09c-4665-a79c-058c578de453`.
Data cutoff: October 10, 2026, 08:06:57 EDT.
Scope: Classic Sunday Main, five generated candidates, one recommended lineup.
The [predeclared protocol](sunday_projection_generation_protocol.md) fixes the
two arms independently of outcomes.

## Projection findings

- All 121 final solver rows have unique canonical player IDs. Mean/P90 and
  P10/P50/P90 consistency checks pass. No populated role, availability, practice
  or market timestamp is after the saved cutoff.
- All 121 have quantile and calibration metadata. This verifies presence and
  consistency, not empirical calibration quality.
- None of the 121 final players or 309 upstream projection-pool rows has explicit
  expected snaps, routes, carries, targets, red-zone share or goal-line share in
  the audited pregame fields. The underlying saved role-context rows also lack
  those explicit estimates, so this is not merely final-pool pruning.
- Separate derived opportunity projections are present: carries for all 14 final
  RBs and targets for all 88 final RB/WR/TE players. They use lagged team volume
  with evidence-supported redistribution. Missing explicit pregame forecasts
  therefore does **not** mean the model has no workload information.
- All nine recommended players have high saved role confidence and no audit
  warning. That confidence must not be interpreted as complete explicit workload
  evidence. Empty practice/official-status fields are not fresh injury clearance.
- Saved projection lineage explicitly says weather is not consumed by the
  projection feature contract. This audit does not establish a weather-related
  forecast error.

The audit is limited to saved evidence. It does not refresh news, verify current
starter status externally, evaluate calibration on unseen outcomes, or certify
entry readiness.

## Controlled generation experiment

The unchanged generator reproduced the exact ordered five saved rosters and
the saved recommendation before either shadow ran. Implementation and solver
fingerprints matched. All three arms passed independent portfolio constraint
validation and completed before the saved October 11, 13:00 EDT kickoff.

| Arm | Change | Changed candidates vs. control | Recommended lineup |
| --- | --- | --- | --- |
| Control | Original weights/template order | 0/5 | Original lineup 2 |
| Mean-led | Mean weight .35 → .55; marginal P90 .45 → .25 | 4/5 | Original lineup 2 |
| Template rotation | Start [1,1] then [1,0], instead of [1,0] then [1,1] | 0/5 | Original lineup 2 |

Solver traces confirm the template order actually rotated. All player inputs,
eligibility, user constraints, candidate count, ownership, correlation/leverage
weights and final selection policy stayed fixed.

The shared recommendation projects **133.07 points**, costs **$49,900**, and has
**232.96 summed marginal player P90**. That last measure is not a lineup P90 or
a calibrated tournament ceiling. The roster is Jacoby Brissett, Chase Brown,
Jaylen Warren, Amon-Ra St. Brown, Michael Wilson, DK Metcalf, Michael Mayer,
Luther Burden III and Commanders DST.

Paid-finish probability and expected return remain unavailable. No outcomes were
used to choose these arms. Because the selected roster is identical, its actual
score and contest finish will necessarily be identical across these arms when
evaluated in the same contest; the changed alternative candidates can still
inform generation research.

## Next evidence gate

Prioritize sourced, timestamped workload estimates and clear missing-evidence
reporting, then test changes with the same fixed final selector. Evaluate actual
GPP paid finishes first, expected net return only with adequate payout evidence,
and tournament upside separately. Use future untouched slates for promotion;
one upcoming slate cannot establish an improvement.

After outcomes are available, score the frozen canonical rosters against the
same actuals and verified GPP paid cutoffs. Report alternative-candidate coverage
separately from the deployable recommendation. Full payout ladders are required
for complete counterfactual dollar-return comparisons. This task saves research
artifacts; it does not add an automatic postgame job or change the app UI.

## Reproduction and validation

Artifacts live in `artifacts/sunday_projection_generation/`: projection audit,
all contracts, candidate rosters, solver traces, prelock timestamps, original
source hash, compact durable replay inputs and live readback proof.

Replay with a **new** output directory:

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_sunday_projection_generation.py \
  --source artifacts/sunday_projection_generation/replay_source.json \
  --output-dir /tmp/sunday-projection-generation-replay
```

The replay input omits unused nested runtime reports; the manifest retains both
the original source hash and the compact source hash. Reproduction requires the
recorded implementation/solver fingerprints. Later replays record their actual
completion time and do not inherit the original experiment's prelock status.

Eight targeted tests pass across audit checks, isolation of shadow changes and
the existing ranking shadow. A read-only database comparison confirms the source
run's recommendation, effective strategy hash and projection-run reference remain
unchanged. No live selector, model, worker, settings or projections were edited.
