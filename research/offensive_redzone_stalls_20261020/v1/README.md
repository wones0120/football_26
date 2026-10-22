# Offensive red-zone stall rate

G23-M06 candidate exact definition is proven non-touchdown terminal outcomes after an observed inside20 native-drive entry divided by all observed entered drives. Both passing and rushing TDs are success once; pass/receiver fantasy scoring is not two touchdown votes. Any later terminal must follow the entry in verified provider order_sequence. A drive that never enters is not included, even if its long scoring play crosses the red zone.

Uses the corrected native_order_redzone_drives_v1 source validated by the reviewed redzone-drive wrapper. Non-TD outcomes require explicit native FG/missed-FG/punt/INT/fumble-lost/downs terminal proof. End-of-file or absent TD flags never prove a stall. Unknown terminal, uncertain entry, or missing native drive keys mask the exact all-eligible rate; known-terminal sample fraction remains separate. No entered drives yields an undefined ratio. This is not a projected kicker probability or scoring-range endpoint measure.

Native offense/opponent binding uses authenticated same-game source team keys, no names or inferred position. Last-up-to8 observed same-season team windows pool drive numerators/denominators, not game rates. Raw/indexed source and compressed parent lineage are authenticated; no new full parent inflate is needed. Actual postlock read/publication times remain current, original historical availability/full-game possession coverage remain unknown. Outputs are descriptive/nonserving, with models/optimizer/app consumers separately pending.

Ten targeted tests cover rushing and passing success once, unknown terminal/entry masks, missing drives, empty logs, pooling, row invariance, future scopes, rejected legacy chronology, before-entry terminal and unsupported end-of-file completion. High definition and actual-artifact approval remain required.

Actual materialization: 158 prior offensive team-game logs,32 pooled windows;517 entered drives=187 proven non-TD stalls+316 touchdowns+14unknown.141 exact game rates,10selected SF/WAS logs. Full/selected byte refs and semantic hashes are in actual_receipt.json. No parent inflation, fetch, database writes, fits or serving activation.
