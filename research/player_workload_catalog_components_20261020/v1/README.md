# Observed workload catalog views: G03, G06, G08

This package reuses the approved25opportunity measurements and the source-proven historical position block. It does not recompute physical plays, fit a model or infer roles. Both immutable inputs must share source snapshot, raw bytehash, event receipt, target period, evidence use and native/canonical identities. Actual publication preserves original provenance plus actual postlock composition time; current-use guards reject these descriptive artifacts.

| IDs | Definition |
|---|---|
| G03-M01/M02/M03/M04/M06 | ScopedQB reported **nonspike** dropbacks, official attempts including spikes, completions, sacks and spikes |
| G03-M07 | ScopedQB scramble count / nonspike dropbacks; a scramble is already one dropback and is not added twice |
| G03-M10 | ScopedQB nonspike dropbacks / all full-source team native nonspike dropbacks, including unmapped canonical backups |
| G06-M01 | ScopedRB official rushing attempts, including any source kneels |
| G06-M02 | ScopedRB nonkneel rushes / all full-team nonkneel rushes, including quarterbacks |
| G06-M03/M04 | Nonkneel carries on preplay first/second down and third down |
| G06-M05 | Nonkneel carries with native preplay ydstogo<=2 |
| G06-M06 | Nonkneel carries in nativeQ2/Q4 with half_seconds_remaining<=120 |
| G06-M07/M08 | Nonkneel carries in Q1/Q2 and Q4 |
| G06-M09/M10 | Nonkneel carries with preplay score differential>0 and<0 |
| G08-M01/M02 | Official player targets and player targets / all full-source team targets |
| G08-M07/M08 | Signed native air yards and player signed air yards / all full-source team signed air yards |
| G08-M09 | Player signed air yards / all official player targets |

Canonical position taxonomy explicitly maps sourceFB toRB; original native position proof remains in provenance. QB and RB interpretations require the same native game/team/period proof, not reputation or passing/rushing identity. Receiving measurements need an observed native receiver, without inventing route participation or availability. Unobserved actors are not inactive zeros.

All exact counts, rates and denominators preserve inherited unknown eligibility, native attribution and source outcomes. Missing passers can make the full-source dropback denominator unknown rather than donating share. Missing receivers keep target and air-yard exactness unknown; aDOT does not ignore potentially unattributed targets. Signed air-yard ratios may be negative or exceed1 and are not probabilities. Zero denominators yield null shares. Full-team budgets and unresolved native identities remain intact; user pools and exclusions do not affect source truth.

G03-M01/M07/M10 explicitly use the nonspike dropback variant; G06-M02 and contextual splits explicitly use nonkneel opportunities. These scopes are disclosed for catalog review. The verified current PBP header has no exact throwaway, designed rollout, play-action, route, first-read or catchability tag; related IDs remain alternate-source verification work, not filled with absent-receiver or snap proxies. Historical completeness/original pregame availability remain unverified. Models and optimizer connections are separately deferred under features-only priority.

The15-test gate covers distinctGSIS/UUID fixtures, physical attempt/dropback accounting, full-source backup and QB carry denominators, QB/RB typed positions, canonicalFB normalization, all RB contextual predicates, signed air yards, unknown attribution/context, duplicate/scope/use/period contradictions and postlock rejection. Actual per-ID coverage and immutable refs are in `actual_derivation_receipt.json`; exact subset, input parity and current-use checks are in `actual_QA.json`.
