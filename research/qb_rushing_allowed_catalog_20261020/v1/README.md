# Official QB rushing production allowed

G15-M10 candidate exact definition: total signed official rushing yards and official carries by explicitly source-proven QBs on the scheduled opposing offense. The primary `value` is total yards, with separately named exact carries and yards-per-official-carry. Kneels and scrambles remain included; the old nonkneel-only position-proof variant remains preserved separately. This does not infer designed rushing, pressure or containment skill.

Native full-source weekly rows join only through canonical team plus REG season/week to the unique native schedule game/opponent. A conflicting supplied native game is rejected; missing or ambiguous schedule binding never guesses an opponent. Multiple QBs add physical counts/yards rather than average efficiency rates. Unknown QB identity/position/cohort, yards or carries mask the relevant exact totals. Native known sums remain separately named. Absent QB rows do not produce zeros. A proved zero official carry count gives an undefined efficiency ratio, not zero YPC.

The newly immutable weekly extract includes60 malformed/missing-native rows; their source position/team/period evidence is inspected so possible QB contributions are not silently dropped. The source-proven native/canonical QB roster and conservative alias collision masks come from the High-reviewed weekly block. Original aliases are not repaired and no player name joins occur.

Actual source composition:1,816 defensive game rows,1,756 exact total-yard and carry observations,10 selected SF/WAS 2026 defensive games,0 unbound native team/week rows. The60 excluded-native source rows remain explicit cohort uncertainty. See actual_receipt.json for source input, schedule provenance, managed full/selected refs and semantic hashes.

The read verifies original immutable weekly component/extract bytes and code lineage, then loads the indexed schedule through its existing source verifier with the real current cutoff. Schedule publication/observation is later than the historical games; original historical pregame availability remains unknown. All new read/publication clocks are actual postlock times. Outputs are retrospective/nonserving; no current model, optimizer or app activation is claimed.

Eight tests cover native opponent binding, multiple QB budget accounting, signed totals, unresolved identity, missing position, malformed-native cohort, unknown team, absent QBs, zero carries and conflicting schedule/game identity. High must adjudicate exact catalog equivalence before register promotion.
