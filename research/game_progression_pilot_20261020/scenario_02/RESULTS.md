# SCENARIO-02 — source repairs and continuation evidence

2026-10-21. Evidence-supported source repairs are implemented; full progression support remains unresolved. This package meets the handoff's source/mechanics/recipe acceptance through explicit observation requirements for continuation. It does not implement or validate a continuation model.

## Implemented

A native single-primary-fumble recovery proof now qualifies clean same-half transitions formerly rejected by the blanket fumble-chain barrier. Require complete source IDs/census, a consistent lost flag, no lateral/penalty/scoring ambiguity, and a qualified matching successor. Self-recovery or a distinct opponent recovery can qualify. Retained teammate recovery, missing recovery, multi-fumble/lateral chains, adjudication conflicts and unqualified successors remain unknown. Original event barriers and raw rows remain in the ledger; discharged transition barriers have separate native proof records. Unknown production channels remain unknown.

Accepted tries whose native penalty was enforced between downs can retain their proven points despite a coarse no_play class, when native results and the following kickoff scoreboard corroborate them. Explicit cancellation and unresolved/reversed replay remain barriers. The kickoff source possession denotes the receiving team; the source defense side is the team taking the try.

Source failures now expose native cycle IDs and source barriers. Censored failures expose observed followup C, generated deadline R, the unobserved interval R-C and the missing-successor requirement. Current action marks remain credited once. Unknown wait-observation kinds stop explicitly. No sampling thresholds, candidate weights, clock defaults or unknown-candidate exclusions were added.

## Validation

295 distinct current test cases are covered: 253 focused parser/source/event cases and 42 adjacent adapter/policy/runtime/integration/precision cases. The focused suite passed 249 cases before a final missing-wait diagnostic guard; the final event suite then passed 33 cases, including four net additional parameter cases. Parser and compilation hashes/AST are unchanged after the source audit; selector AST is unchanged from SCENARIO-01. See VALIDATION.json for exact commands and timings. No services or database were required.

## Measured result

| Static cached TRAIN audit | Recorded result |
| --- | --- |
| Cycles retained in identical source order | 43,852 |
| Previously source-certified transitions | 42,953 |
| Now source-certified transitions | 43,197 |
| Additional proven transitions | 244: 239 single-fumble, 5 accepted tries |
| Remaining unknown TRAIN transitions | 655 |
| Original 196 source-stop draws whose terminal source transition is now proven | 56 |
| Original source stops still unresolved | 140 draws / 126 distinct source cycles |
| Original censored-successor stops still unresolved | 72 draws / 68 distinct source cycles |
| Original complete states / supported joint-law paths | 2 / 0, unchanged historical evidence |
| New simulations / fits / accuracy evaluations | 0 / 0 / 0 |

The 56 repaired terminal draws are a source-certification finding, **not newly completed paths**. Their earlier sampled candidate pools could contain newly certified candidates too; no path or forecast was regenerated. All 320 original smoke records remain, including 270 finished records and 50 cap/failure placeholders. Original v3 manifests, checkpoint, results and smoke summary are hash-verified unchanged. Kernel cycle starts, native contexts, priors, endpoints, waits and production values are identical in the audited newly compiled library; only certification/barriers/provenance differ. The changed library was transient, not published over the old artifact.

Initial source audit: 10.455s, 239 fumble transitions proven. A substantive kickoff-orientation correction justified a separate changed audit: 10.498s, including 4.555s reconstruction, under its 60s cap. Both receipts remain. They are static source audits rather than unchanged simulation retries. See [initial receipt](AUDIT.json), [current receipt](AUDIT_KICKOFF_ORIENTATION.json), [recipe](RECIPE.md) and [validation receipt](VALIDATION.json).

## Remaining evidence

The [source-gap inventory](SOURCE_GAPS.json) lists every remaining source-stop cycle and its saved source evidence. Barrier counts overlap: 92 of the 140 remaining source-stop draws still involve incomplete fumble chains, 42 unresolved replay, 34 lateral flags, and smaller physical/scoring/penalty conflicts. Counts are not additive. Native recovery IDs alone do not settle a multi-event/lateral chain or retained-teammate yard accounting.

The 72 censored draws include 31 native kneels, 14 passes, 11 runs, 11 field goals, two punts, one spike, one extra point and one kickoff. Endgame action policy and stopping are informative. Extending a source half-ending wait or drawing a different exact successor after seeing censoring would introduce unsupported assumptions and change the joint law.

The [continuation observation requirements](RECIPE.md#censored-continuation-explicit-observation-requirement-no-fitted-model) specify play-end physical/enforcement and clock-running state, timeout use, native action/successor linkage, and sufficiently supported longer followup under comparable action/clock/score/policy context. Some timeout and clock snapshots exist in the cached projection, but this package does not establish play-end timing, clock restart policy or an identifiable conditional continuation tail. Any later model needs a frozen joint policy/censoring assumption and chronological TRAIN validation; artificial-censor tests alone cannot establish natural endgame transportability.

No live behavior, settings, saved lineups or 2026 labels changed. High and monitors remain off. More unchanged sampling cannot resolve these missing observations. SCENARIO-03 label work is independent; SCENARIO-04 must not be presented as a supported forecast or accuracy evaluation while these gaps remain.
