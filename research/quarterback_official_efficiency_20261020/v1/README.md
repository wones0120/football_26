# Source-proven QB official rushing efficiency

G05-M05 is signed official weekly rushing yards divided by official weekly carries, scoped only to explicitly source-proven native QBs. Kneels and scrambles remain in the denominator; the previous nonkneel-only QB variant stays preserved separately. There is no designed-QB-rush or pressure attribution claim.

The wrapper uses the High-reviewed immutable weekly effectiveness source. It checks native prior REG week/team grain, explicit QB scope, canonical UUID spelling and exact same-row numerator/denominator consistency. Native alias collision masks and identity requests carry through. Missing and zero carry exposures remain undefined; negative yards are neither clipped nor replaced. No current roster/availability inference is made.

Actual composition verifies immutable weekly component bytes, its producer hash and its original field-extract byte hash, retaining all real read/publication and original import clocks. Newly frozen/revised source evidence does not establish original historical pregame availability. All outputs are postlock descriptive and current serving is ineligible. No source fetch, model, optimizer or app consumer is claimed.

Tests cover signed official-inclusive counts, non-QB exclusion, missing/zero denominator, strict prior scope/current-use restriction and source ratio contradiction. Actual materialization is complete; see actual_receipt.json for full/selected refs and exact coverage. Catalog promotion remains pending High review.
