# Workload evidence v2 — original observations versus allocated proxies

The shared evidence builder now distinguishes original measured history from transformed allocations. This corrects false observed labels; it does not promote a new player model, allocator or tournament selector. No projection means, marginal intervals, Captain qualification, eligibility, user preferences or saved lineups were changed. No service reload or operational optimization was performed.

## Implementation

New `workload_evidence_v2` history uses `pregame_base_targets_mean_3`, `pregame_base_carries_mean_3` and corresponding original target/carry shares, with existing coverage flags and projection/feature lineage. Missing original bases remain `original_history_unavailable`. An original measured zero remains zero; a missing or filled value cannot become an observed zero.

Adjusted counts/shares remain separately available under typed `derived_proxies`, including `allocated_targets`, `allocated_carries` and allocated shares. Existing projected-target/carry proxies also retain their values. They are not independently calibrated count forecasts.

Explicit pregame inputs carry their original producer source and observation clock. Shared Analyst consumers give an attributed, time-checked producer input precedence, then original measured history. A numeric input without attribution cannot silently qualify as a producer forecast. Consumers trace evidence kind and source field. Allocated proxies remain available for labeled conditional sensitivity; they cannot certify observed role/usage in the new scenario planning contract.

Both legacy v1 and new v2 packets remain readable. Old packets retain their exact values, version and original consumer behavior; no new base history is backfilled into saved runs. Learning manifests now report the actual saved version instead of stamping every saved packet with the current version. Mixed versions remain explicit. The offline packet validator/schema and production packet validator accept both versions and validate v2 original-history attribution.

Captain workload qualification already used original base evidence; that policy and its thresholds were not changed. The source allocator remains default-off `team_window_v2` research. The existing default/model truth and all user controls remain unchanged.

## Frozen research comparison

The comparison protocol was frozen before measurement mapping. It uses the original Sunday Main run `398efe88-a871-47fa-a4f1-4d3e9924a825`, projection `c8869a96-440c-4c36-aead-3614d6ef4d97`, without outcomes, model fitting or candidate solves. Original source packet v1 and new v2 research children are separate files.

|Invariant or effect|Result|
|---|---:|
|Full canonical source actors retained|513 / 513|
|Original eligible solver players|137|
|Excluded actors retained with original reasons/model assessment|376|
|Original stored feature rows recovered by canonical ID/game/projection|285|
|Actors without recovered feature rows, retained as unknown|228|
|Eligible players with recovered original features|137 / 137|
|Known original-history count channels, v1 / v2|526 / 526|
|Historical count values corrected|271|
|Selected measurement values changed|273|
|Recovered allocated counts conflicting with old saved allocated observations|0|
|FP moments, exclusions and preferences changed|0|

Counts are two channels per actor, including unsupported/nonapplicable positions; they are not independent games or newly produced forecasts. The same coverage count with different values is the intended semantic correction. A generic v2 packet can still have known snap history while its count history is unknown; do not collapse evidence groups into one blanket confidence claim.

Representative changes below are selected by absolute difference in the historical measurement, not by actual points. Existing model inputs/FP means remain unchanged; the new values are observations, not authored next-game workloads.

|Canonical player display|Channel|Old v1 “historical” value|New original-history value|Original optimizer inclusion|
|---|---|---:|---:|---|
|Jeremiyah Love|Carries|6.562|15.667|Excluded|
|Kyle Monangai|Carries|10.185|16.667|Excluded|
|Quinshon Judkins|Carries|9.886|16.333|Excluded|
|Kenneth Walker III|Carries|15.019|21.333|Included|
|Tony Pollard|Carries|9.415|15.667|Included|
|Braelon Allen|Carries|8.512|14.000|Included|

Excluded actors retain their model assessment and opportunity evidence. A user exclusion never transfers these counts to another player. Raw observed counts do not establish a future role after a trade, injury or depth change; those mechanisms remain separate evidence requirements.

The original compact saved pool did not retain every original base field. Corresponding existing feature rows were recovered read-only with IDs, content hash, capture time and creation clocks preceding the original decision. This is a new research child using recovered stored features, **not** an original packet rewritten after lock or independent proof of historical provider availability. All allocated values agree with the saved observations where comparable. Missing sources remain explicit rather than reconstructed.

## Football meaning and limits

A role transport should not treat an allocated 6.56 carries as the same observation as a measured 15.67 recent carries. Correct provenance allows the simulation/research layer to distinguish history, allocation assumptions and producer-issued forecasts. It does not establish that repeating 15.67 carries is likely tonight, that a historical analogy is calibrated, or that its lineup wins more often.

The preceding identical-source allocation experiment remains negative/mixed at the FP level: improved RB count error did not improve RB FP error, and WR count/FP error worsened. That result remains a reason to keep the allocator inactive. No weighting changes or outcome-selected role thresholds were added here. Additional football/chronological validation is required before promoting any downstream model or selector change.

## Validation and known fixture correction

Focused tests cover original-versus-allocated separation, measured zero/unknown/future evidence, attributed producer precedence, malformed clock rejection, legacy packet identity/version preservation, exclusion invariance, new proxy-only role abstention, and v2 false-history rejection. Existing solver/FP evidence-serialization invariants and Captain policy checks remain exercised.

An existing full-optimizer Captain fixture failed before the shared evidence builder ran: its locked synthetic WR lacked the raw measured-role facts required by the current Captain policy. A spy confirmed zero evidence-builder calls on that failure. The fixture now supplies explicitly synthetic, timestamped measured role evidence so the existing test can reach its intended saved-report path. No real player evidence or application Captain policy was changed. Final commands/counts are recorded in validation.json.

No new fitting ran for this semantic comparison. The earlier parity diagnostic’s six fixed isotonic anchor refits via its existing FP helper remain disclosed in `/private/tmp/allocation_parity_diagnostic_20261019/v1/REVIEW.md`; that helper was not called in this task.

## Artifacts

`comparison.json` retains canonical per-channel old/new values and typed basis for every actor; `new_v2_evidence.json` retains the separate research children. `recovered_original_feature_fields.json` records source linkage/missingness; `summary.json` is the compact hash-bound summary. `PROTOCOL.md`, `compare.py` and `read_features.py` reproduce this read-only mapping audit. These are research artifacts, not saved operational lineups, exports or entry clearance.
