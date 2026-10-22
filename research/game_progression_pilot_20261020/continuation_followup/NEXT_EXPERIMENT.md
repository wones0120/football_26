# Next experiment: clock and action policy together

Status: design boundary for the next bounded implementation; no model, acquisition job or simulation dispatched by this document. Previously inspected outcomes remain retrospective.

## First implementation slice: observation contract

Create a separately versioned research observation ledger linked by native game/play ID and immutable source reference. Preserve the original cycle library and baseline recipe. For each action and intervening control event, distinguish:

| Observation | Required interpretation |
| --- | --- |
| Snap state | Half/quarter/game clock, full score differential, possession, field/down/distance, timeouts by side and native action identity. |
| Play-end state | Independently bound terminal field/possession, clock at play end, scoring and enforcement; never a next-snap timestamp relabeled as play end. |
| Clock control | Running/stopped status and cause, restart, timeout use, runoff/correction and required untimed action. Missing fields stay unknown. |
| Followup | Joint next action identity/pre-state and next-action wait, or an explicit censor reason/horizon. |
| Provenance | Source ID/hash, native linkage, source availability and derivation status; reconstructed labels cannot become original-vintage evidence. |

Start by carrying existing native timeout observations into the separate ledger and inventorying source/control records needed for the other fields. A generated timeout budget needs its own supported transition rule; do not reset it from a newly sampled historical game. Use explicit support statuses so known pre-snap counts cannot imply a known terminal clock. The 15 deferred source cases can remain unresolved in this ledger.

## Candidate model boundary

Model the joint **action choice, terminal event and next-action wait** conditional on football state and clock policy. The current exact physical-only control remains a baseline comparison. A proposed model must declare which clock/timeout/score facts are essential and keep their absence explicit through any fallback. It must not sample an endgame action first and then attach an unrelated ordinary-play wait.

Kneels, spikes and timeout decisions need policy support in the generated state. A short source horizon is informative about those decisions; a marginal survival fit cannot establish independent censoring. Pooling across physical/action states would require declared football mechanisms and separate empirical validation. Preserve unresolved outcomes and unknown tail mass instead of normalizing over known continuations.

## Bounded validation proposal

Before any fit, freeze a chronological whole-game TRAIN2023 split, feature/conditioning definition, censor mechanism, unknown-mass treatment and an explicit one-job cap. Do not use 2026 results to choose the mechanism. A first observation-contract audit should use the same cached TRAIN projection, one <=30-second pass, exclusive output identity and no automatic retry. Stop at an evidence inventory if required observations cannot be obtained.

Only after the contract has supported records, assess artificial censoring of otherwise observed trajectories in later disjoint TRAIN games. Measure wait survival/coverage, next-state validity, unknown coverage and opportunity/scoring conservation separately, by clock, score and action class, with whole-game dependence retained. Include natural-censoring distribution differences. Artificial censoring alone cannot validate unobserved endgame tails.

Any later changed smoke needs its own frozen reason, dispatch scope and cap. No higher-precision run or live activation follows automatically. Success means supported progression and honest unknown accounting, not a higher fraction of paths made to finish.
