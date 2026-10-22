# Continuation followup: bounded evidence audit

The broader continuation problem includes an action-policy mismatch, not just a missing wait value. In the newer SCENARIO-04 cohort, **29 of 32** censored stops transported a source action across the existing <=120-second clock stratum, and **16 of 32** involved kneels. This does not prove every selected action impossible, but it shows why borrowing a longer wait alone is insufficient.

One cached audit took **1.623 seconds** under a 30-second cap. No reconstruction, simulation, fit, source download or live change ran. All prior evidence hashes were preserved. The 15 selected source-state cases are separately [deferred known limitations](../source_state_followup/DEFERRED.json); their states remain unknown and they remain in candidate mass.

| Saved cohort | Censored records | Distinct source cycles | Crossed <=120-second stratum | Kneels | With exploratory longer-followup matches |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original v3 | 72 | 68 | 65 | 31 | 5 |
| Changed SCENARIO-04 | 32 | 31 | 29 | 16 | 1 |

These cohorts are dependent, separately identified research records, not independent evaluation samples. Do not sum them into a completion rate. Unobserved gaps range from 7–1,733 seconds in v3 and 9–1,583 seconds in SCENARIO-04.

## What the matches mean

The read-only diagnostic retains exact physical state, native action class/flags and both sides' production/score marks, excludes the stopped source's entire game, then counts observations matching the stopped source's half/score sign with source start clock >= the generated horizon. It retains uncertified and censored candidates in the counts. Exact observed waits beyond the censored horizon count as candidate followup evidence; they are not imputed successors.

Only one of the 32 newer stops has such a match: a field-goal source with C=3 seconds and a generated deadline of 12 seconds has one other-game exact followup observation under these checks. This remains insufficient to identify its continuation law. Exact mark matching is deliberately restrictive and is not a proof that broader statistical pooling cannot work. The counts condition on the stopped source's context, not a reconstructed generated pre-action context; generated policy support is not established.

## Available evidence and missing state

All 43,852 cached TRAIN cycle rows contain non-NULL source home/away timeout counts. The current compiled cycle and generated runtime state do not carry timeout state or its evolution. Availability of pre-snap timeout values alone does not prove their enforcement or the policy used afterward.

The cached projection does not bind explicit play-end clock/terminal state, clock running/stopped reason, or restart/runoff enforcement to the required continuation transition. Next-action time and drive boundary metadata cannot substitute for these observations. The current broad selector fallbacks can drop clock/score context; the control intentionally retains only physical-state matching. Both remain unchanged as recorded baselines.

## Decision and next work

Proceed with the [clock/policy observation contract and bounded prototype design](NEXT_EXPERIMENT.md), rather than fitting a marginal waiting-time curve or substituting an exact donor after drawing a censored event. Retain unknown continuation mass and count action credit once. Do not ban kneels by a one-off rule, filter to certified sources, copy a source half ending or inflate precision to mask unsupported transitions.

**The continuation problem is not resolved by this audit.** It now has measured failure categories, a reproducible support diagnostic and a concrete next implementation boundary. SCENARIO-05 precision and accuracy comparisons remain gated.

Validation: **44 tests pass in 0.60 seconds**, including 11 new audit cases plus 33 event-boundary regressions. Tests cover unknown mass, same-game exclusion, exact joint marks, source-side normalization, nested context/horizon counts, invalid waits, strict censor horizons and immutability. See [AUDIT.json](AUDIT.json), [RECIPE.md](RECIPE.md) and [VALIDATION.json](VALIDATION.json).
