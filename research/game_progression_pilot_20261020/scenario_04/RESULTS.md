# SCENARIO-04 — bounded changed mechanics smoke

Completed 2026-10-21. One separately identified changed run finished all 106 frozen dispatch cases within the 30-second cap. It produced nine complete regulation states and zero supported joint-law paths. No forecast accuracy or live-readiness claim follows.

## Scope and result

| Frozen disposition | New dispatches | Complete states | Unknown source state | Unknown censored successor |
| --- | ---: | ---: | ---: | ---: |
| Prior terminal transition newly source-certified | 56 | 7 | 29 | 20 |
| Prior cap/failure placeholder | 50 | 2 | 36 | 12 |
| Total new run | 106 | 9 | 65 | 32 |

The other 214 original slots were explicitly skipped: 140 unchanged source-state failures, 72 unchanged censored failures and two original completions. All 320 slots have origin-linked audit rows. The original 270 finished records and 50 cap/failure placeholders remain byte-for-byte unchanged; the new dispatch is not an extension of the original run. Some prior placeholders may have started without a durable result; they are not described as all never-started.

All 56 changed-case uniform streams and selected-cycle/tier/pool-size/clock prefixes matched their original records. Each previously failing, now source-certified transition transferred; 49 of those paths subsequently stopped on another unknown source or censored successor. The 50 placeholder cases have no durable prior terminal result to compare.

Preparation reused the saved all-TRAIN audit to derive the separately bound 43,852-cycle library with 43,197 certified transitions. Candidate identity/order, physical/context support, empirical probabilities, production, waits and endpoints remain unchanged; audited certification/provenance changes and the existing index are used. The six unscopable source threats and one unknown opening remain. Generation loaded no actual-count labels, refreshed no sources and ran no fit.

## Channels and support

Among the nine new complete states, both sides have known full-path pass attempts, carries and physical plays in all nine; targets in one; possessions in five. Passing/receiving/rushing yards and TD channels are known in all nine. These are path-completeness counts, not completed game/arm forecasts.

Complete 32-path game/arm channel forecasts: **zero for every channel**. Complete supported joint-law paths: **zero**. The selected changed/previously unfinished slice cannot supply a complete 320-path population by combining old and new runs or averaging successful subsets. MAE/RMSE/bias and improvement rates were not computed; accuracy N remains zero. Actual-count label completeness from SCENARIO-03 does not resolve source or continuation support.

Selected unfinished paths: zero. Started but unfinished: zero. Undispatched selected paths: zero. The 214 intentional skips retain their explicit dispositions rather than zero totals. No censored wait was extended, no unknown candidate was dropped and no certified-only renormalization occurred.

## Bounds, evidence and validation

- Preparation took 2.290s under a 30s cap.
- The single smoke took 1.407s for computation/loading/dispatch and 1.443s through audit publication, under a 30s compute cap. Publication tail: 0.036s. Maximum 106 dispatched cases, 400 actions/path, original seed 17 and 401 uniforms/path. No retry or cap increase.
- Sixteen isolated runner tests passed in 0.72s, covering dispatch selection, native proof consistency, exact original uniform hash, source-prefix checks, skips, channel masks, cap/failure accounting, output-overwrite rejection and partial journal tails. Tests use fake rollouts and temporary outputs.
- Post-run checks verified all 320 origin digests, frozen code/recipe/input references, all 106 uniform streams, all 56 repaired prefixes, complete-state boundaries and known count conservation. Original scenario results/receipts remain hash-verified unchanged.

See [frozen recipe](RECIPE.md), [manifest](MANIFEST.json), [summary](changed_smoke_1/SUMMARY.json), [all 320 origin-linked rows](changed_smoke_1/paths.jsonl), [durable starts](changed_smoke_1/attempts.jsonl), [106 new results](changed_smoke_1/results.jsonl) and [validation receipt](VALIDATION.json). Implementation/test/audit elapsed time is recorded separately from the bounded job times. Re-executing prepare/run is intentionally rejected because outputs already exist.

## Next gate

SCENARIO-04 acceptance is met. SCENARIO-05 remains gated: progression/support is not yet established, so no larger precision run is justified. Use the SCENARIO-02 source-gap inventory and conditional wait/successor observation requirements to address remaining support before proposing another separately bounded experiment. The new 65 source-state and 32 censored stops are mechanics traces available for that diagnosis, not permission for unchanged reruns.

Live projections, optimizer defaults, user settings, saved/entered lineups, aliases and databases were untouched. High, monitors and paused automations remain off.
