# Clock, timeout and action-policy observation contract v1

Implemented a separate research ledger, [LEDGER.jsonl.gz](LEDGER.jsonl.gz), with [contract code](contract.py), [frozen recipe](RECIPE.md) and [manifest](MANIFEST.json). One cached extraction completed in **4.120 seconds** under a 30-second cap. No new sources, reconstruction, model fit, simulation, runtime changes or live activation were performed.

## Coverage

| Ledger observation | Count |
| --- | ---: |
| Original source rows retained in order | 49,665 |
| Uniquely linked frozen TRAIN cycles | 43,852 |
| Linked cycles with validated pre-event timeout pairs | 43,852 |
| Native control rows retained | 3,493 |
| Other retained rows without an action/control classification | 2,320 |
| Validated regulation pre-event clocks | 49,393 |
| Explicit overtime clock rows | 267 |
| Unknown/conflicting clock rows | 5 |
| Validated oriented pre-event score snapshots | 47,027 |
| Unknown/unoriented pre-event scores | 2,638 |
| Frozen exact-next-action intervals | 43,309 |
| Frozen right-censored intervals | 543 |

Every source row has a projection-hash/zero-based-ordinal identity. Native game/play matching is unique in this cache; missing/duplicate identity is nevertheless handled explicitly by the contract and tests. A manifest binds the original source lineage, capture/read times and revised-historical availability. These observations do not prove original pregame availability.

## What is supported

- Source pre-event quarter/half/game clocks are validated for consistency; control snapshots are not called snaps. Overtime stays separately identified.
- Native home/away timeout budgets are validated as integers from zero through three. Offense/defense orientation requires coherent native teams. A zero is known; missing, invalid or ambiguous values are not filled.
- Full pre-event score differential uses possession-side pre-scores, never post-play or final totals. Native action flags and actor IDs remain observed source examples, with no inferred action-policy probability.
- Saved cycle waits, next-action/boundary endpoints, source certification/barriers and joint production/scoring marks are carried separately. The frozen comparison library retains 43,197 certified and 655 uncertified transitions. Later source repairs are separate evidence; this extraction does not replace that library.

The ledger has no live consumer. It cannot reset a generated timeout budget from another historical game's observations.

## Missing evidence remains explicit

All records retain unknown play-end clock/terminal field/possession/enforcement, running/stopped cause, restart/runoff, timeout use/team, clock corrections and untimed-action enforcement. A next-action endpoint or drive end_clock_time is not a play-end observation. Pre-event timeout counts do not prove a timeout-use event.

The compiled library does not carry a general native successor play ID. The ledger therefore records its endpoint/wait but leaves the native successor link unknown, rather than inferring it from source adjacency or clock equality. Native source order and projection ordinals are available for a later independently validated link.

Generated timeout evolution and action-policy support remain unknown. The 15 deferred source cases and all prior runs/receipts are preserved by hash. No complete-path, precision, accuracy or continuation-support claim follows from this contract.

## Validation and next boundary

**75 tests pass in 0.66 seconds**: 31 new observation-contract cases plus 44 continuation/event-boundary regressions. Checks cover invalid/missing values, true zero budgets, clock inconsistency, overtime/controls, native duplicate identity, side orientation, pre-score attribution, immutable source inputs and rejection of inferred terminal/policy support. The builder validates every emitted record, accounts for every input row and library cycle, and verifies preserved hashes before publishing the success manifest. See [VALIDATION.json](VALIDATION.json).

Next work is a bounded source/control-linkage investigation against the [missing-observation inventory](MANIFEST.json), especially native timeout events/team, explicit play-end clock and restart/enforcement records. Add separately identified observations with source lineage; do not reinterpret the existing unknown fields as known. Stop at an evidence inventory if those records are unavailable. A joint clock/action/wait model still requires declared assumptions and chronological whole-game validation before fitting or another changed smoke. SCENARIO-05 remains gated.
