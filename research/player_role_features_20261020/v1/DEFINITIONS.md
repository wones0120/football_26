# Full-team availability and role features: first A02 slice

`full_team_role_features_v1` is a pure feature derivation, with no model, optimizer, forecast, source download or user-preference effect. The full 320-candidate program remains open. This slice implements ten exact catalog definitions at a supplied, scoped canonical source boundary; actual source coverage remains candidate-specific.

| IDs | Exact implemented value | Unknown conditions |
|---|---|---|
| G17-M01 | Canonically resolved categorical official/game designation; original facts and conflicts retained | Blank/ACT does not mean no designation; missing, stale, conflicting or wrong-scope facts remain unknown |
| G17-M02 | Dated DNP→LP→FP participation sequence and ordinal last-two-day difference | Two actual practice dates required; retrieval clocks cannot stand in for practice dates; contradictory same-day reports remain unknown |
| G17-M05 | Explicit source depth order, integer starting at one | A backup/starter role label alone is not converted to an invented numeric depth order |
| G17-M10 | Original documented workload restriction, including absent numeric limits | Missing restriction does not establish unrestricted workload; no fabricated percentage |
| G18-M01 | Unique sourced starting QB's participation availability | Missing/ambiguous starter or unknown availability remains unknown; Q policy is separate |
| G18-M03–M07 | Full-source unavailable STARTER counts for OL/DL, and all-personnel unavailable counts for CB, safety and linebacker | Exact values require a scoped complete roster manifest and known statuses for the entire relevant position group; unknown source positions or OL/DL unit-role classification also prevent exact counts; otherwise null with known unavailable lower bound |

Every fact requires canonical UUID, current team/position, explicit season/week, source identifiers/URI and ordered observed/received/publication clocks. The existing canonical factual composer/resolver is reused. Fresh reserve participation prohibitions retain the separate game designation rather than converting reserve or Q into healthy status. Unresolved native actors are emitted to an identity-review request list; upstream ingest remains responsible for durable queue persistence and immutable byte verification.

Team counts use the supplied full roster before user exclusions. A salary-only subset does not prove a complete roster. Empty exact groups may yield zero only if that complete roster assertion is supported; otherwise zero is not invented. Current player/team facts are derived features, not next-game opportunity forecasts.

Twenty-seven focused checks cover exact/lower-bound counts, missing ACT/designation, practice dates/conflicts, literal depth/restriction values, future/stale/wrong-week/wrong-identity/wrong-position/unscoped inputs, unresolved actors, duplicates, reserve versus Q separation and source recapture/preference invariance.

Feature code and fixtures are implemented. An actual preserved60-player context/2,357-fact boundary was derived after lock: nine official designations are known; it contains no dated practice, explicit numeric depth-order or restriction facts, and is salary-scoped rather than a full-team roster. Exact personnel counts correctly remain unknown. This verifies actual boundaries and gaps rather than claiming complete source coverage. High review is pending. Model and optimizer consumption are explicitly false. No remaining A02 candidate is completed by this slice, and no generic unknown envelope is counted as an implemented missing measurement.

Review corrections: effective/modified clocks on depth/restriction facts cannot be malformed or future. OL/DL starter classification requires current sourced role facts; backups are not counted as starters. Unclassified source positions and unresolved native facts mask exact group denominators. Official designation values require an official NFL/club source; native values remain preserved separately. Roster ACT alone does not establish game availability.

Final identity/group corrections: canonical UUID spelling is normalized before duplicate detection and fact matching. OC (center) belongs to the OL starter group. Native unresolved facts retain review requests rather than disappearing from roster coverage.
