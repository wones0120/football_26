# G05 scoped QB rushing measures

This pure wrapper composes two authenticated immutable component blocks: the approved25opportunity measurements and player effectiveness/position-proof measurements. They must share the exact frozen source snapshot, source bytehash, target period and evidence-use state. Native game/team/player and canonical UUID must agree. The caller authenticates both artifacts and their original parent; self-declared source markers alone do not authenticate evidence.

Only actors with source-proven historical QB position on the same native game/team/period are included. Unknown positions and observed non-QBs are explicitly excluded from this QB interpretation, never inferred from rushing or passing identity. Full-team opportunity budgets and identity requests are retained.

| ID | Measured definition |
|---|---|
| G05-M02 | Source QB scramble count on nonkneel official rushes |
| G05-M03 | Source QB kneel count on official rushes |
| G05-M05 | Explicit nonkneel native rushing-yards/attempt variant |
| G05-M06 | Explicit providerEPA>0/nonkneel rush success variant |
| G05-M07 | Source first_down_rush count on nonkneel rushes |
| G05-M08 | Nonkneel rushes with preplay yardline0–20 |
| G05-M09 | Nonkneel rushes with preplay yardline0–5 |
| G05-M10 | Source rushing-TD count on nonkneel rushes |

G05-M01 exact designed-QB calls and G05-M04 scramble-under-pressure denominators remain source gaps. The existing nonscramble-or-other count is labeled supporting evidence, never renamed designed calls. Kneels remain separate from nonkneel production. Missing eligibility, native attribution or outcomes keep exact counts/rates null; observed lower bounds and known-attributed sample rates remain separately available. An observed QB with no source rush opportunities may have known within-log zero only if team/native eligibility is complete; absent/unobserved players are not inactive zeros.

Native periods are strictly before the target. Full-game completeness and original pregame availability remain unknown; actual inputs/outputs retain their postlock descriptive/nonserving markers and original read/derive/publication provenance. No model, forecast, optimizer or current availability claim follows. Tests cover all mapped measures, native/position scope, unknowns, lineage/identity/version/use contradictions, future period, source order/material changes and current-use rejection.
