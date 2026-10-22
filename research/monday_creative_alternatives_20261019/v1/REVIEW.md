# Monday Captain: McLaurin, Watkins and complete alternatives

Research comparisons only. Saved run 8a4a1d21-4b13-4ed0-baf4-b48d95da967e and its four rosters remain unchanged. Frozen projection f7cc2ef6-812d-4d38-91aa-fa5b60754f05, source cutoff 2026-10-19T13:49:47.743907UTC. No operational generation, model change, preference override, submission or download occurred.

## Verified explanation

**Terry McLaurin:** $8,000 / 10.496 base FP mean; excluded solely by user_excluded_questionable on the Captain salary source. This is not a salary rejection or a model judgment that he lacks a role. The official Oct17 full game-status report has limited/DNP/limited practices and no game designation, while the older native Captain file still says Q. Roster ACT does not by itself prove game health; the final injury table is the stronger evidence here. These sources disagree and the operational run preserved the native-Q preference binding. No override was applied. [Official final report](https://www.commanders.com/news/game-status-commanders-49ers-week-6).

**Jordan Watkins:** canonical 353a36c9-e214-48e2-81bc-c6a8ed308a02; native FLEX44533103/CPT44533163. The available canonical GSIS00-0040172 raw data has two 2026 targets, both Week3, for two catches/60yards. Official SF season stats corroborate two catches/60yards, but do not provide targets. His saved 1.6667 historical targets average uses last observed records: 2025W8=2, 2025W9=1, 2026W3=2. Code attach_lagged_opportunity_features legacy_v1 selects last three observed records across seasons; it is not a current-season three-game average. Missing weekly rows are not asserted to be measured zero. The 0.7998 projected_targets field is an allocated proxy, not a supported forecast of an expanded role. Saved role is expected_backup, no role_change, no explicit expected targets/routes. Deebo OUT alone does not substantiate a target upgrade. Watkins is cheap FLEX support in this model, not qualified Captain: the saved shortlist blocks him at CPT. [SF season stats](https://www.49ers.com/team/stats/).

**Drew Stevens** is the correct name (FLEX44533091/CPT44533151), not Jake Stevens.

## Complete matched-input alternatives

|Comparison|Captain|Five FLEX|Salary|Sum of FP means|
|---|---|---|---:|---:|
|highest_mean_control|Brock Purdy|Drew Stevens, Jordan Watkins, Jayden Daniels, Chig Okonkwo, Christian McCaffrey|$49,600|76.345|
|no_watkins|Jayden Daniels|Drew Stevens, Brock Purdy, Chig Okonkwo, Dyami Brown, Christian McCaffrey|$49,800|76.289|
|kittle_flex_no_watkins|Jayden Daniels|Drew Stevens, Eddy Pineiro, George Kittle, Chig Okonkwo, Christian McCaffrey|$49,800|71.258|
|kittle_captain_no_watkins|George Kittle|Jacob Cowing, Jayden Daniels, Brock Purdy, Dyami Brown, Christian McCaffrey|$49,700|68.867|
|cmc_captain_no_fringe_sf_receivers|Christian McCaffrey|Jayden Daniels, Brock Purdy, Chig Okonkwo, Dyami Brown, Antonio Williams|$49,900|70.928|
|conditional_mclaurin_no_watkins|Jayden Daniels|Drew Stevens, Eddy Pineiro, Chig Okonkwo, Christian McCaffrey, Terry McLaurin|$49,600|71.720|

**Practical first alternative:** no_watkins is already operational saved #3. Compared with recommended #4 it changes Captain Purdy→Daniels, replaces Watkins→Dyami Brown and spends $200 more; all other players remain. Its 0.056mean deficit is negligible as evidence of superiority. It removes the specific Watkins concern but retains another cheap receiver with uncertain volume. The saved recommendation remains #4; this audit does not hand-pick a new app recommendation.

**Kittle FLEX:** drops Purdy and Watkins to afford Kittle plus both kickers. It can succeed through meaningful Kittle receiving, CMC production, Daniels rushing/passing and stalled drives producing kicks. Kittle and CMC compete for SF opportunities, and leaving out Purdy sacrifices his yardage/TD scoring when Kittle succeeds. Mean cost is 5.086 versus control. It reduces fringe-receiver dependence but does not prove a better tournament outcome.

**Kittle Captain:** current shared constraints require the supporting Purdy for a receiving Captain. Keeping both QBs and the required CMC forces Cowing and Dyami; this merely moves cheap-receiver risk. Mean cost is 7.478. Kittle qualification is supported by original historical6.333targets/24.54%targetshare/92%lastsnaps, not the allocated2.945proxy. A receiving Captain can outscore his QB through receptions/yardage/TD concentration, but no win probability is established.

**CMC Captain without fringe SF receivers:** CMC CPT; Daniels/Purdy/Okonkwo/Dyami/Antonio FLEX. This emphasizes CMC rushing/receiving and TD concentration plus a Washington response; it removes Watkins/Cowing/Cooks but places three Washington receiving options around Daniels. Those opportunities are shared, not independent. CMC rushing TDs can reduce Purdy passing payoff. Mean cost5.417; preserving both QBs and CMC at CPT leaves insufficient salary for Kittle/McLaurin under current eligibility. No CMC projection boost was invented.

**Conditional McLaurin FLEX:** explicitly not current-eligible or saved. A bounded conditional comparison waives only his stale native-Q exclusion for FLEX while retaining original CMC-required and all other saved constraints. Daniels CPT; Stevens/Pineiro/Okonkwo/CMC/McLaurin, $49,600, mean71.720. It replaces Purdy+Watkins with McLaurin+Pineiro and changes Captain to Daniels. It supports Washington passing to its established receiver, but McLaurin/Okonkwo share targets, and the two kickers need usable drives. It gives up all direct Purdy scoring and has 4.625lower mean. This is a FLEX-only conditional subset, not a claim of best McLaurin Captain construction or a global conditional optimum if leadership eligibility were recomputed.

## Method, settings and limits

Enumerated766 legal standalone current-pool rosters by checking every saved LP constraint, without solving or changing operational records. The highest-mean enumeration exactly reproduces saved recommended#4, providing a useful validation. Conditional263 McLaurin-FLEX rosters append his frozen original projection/salary to generic WAS-WR FLEX constraints; the original CMC leader requirement is retained conservatively. No additional Captain qualification for McLaurin is asserted. Exact canonical rosters/base means, source hash and method are in comparison.json/enumerate.py.

All current constraints were retained: $50k cap, $1700basefloor, max4/team, canonical uniqueness, exact Captain/FLEX slots, Captain shortlist/position exceptions, receiving-Captain QB support, season leader requirement, QB construction and offense-vs-DST restrictions. User player100%/Captain50%/four-entry settings remain unchanged. These are standalone diagnostic alternatives, not a new four-entry portfolio; they do not independently satisfy a four-entry exposure constraint. The existing saved portfolio does: Purdy2/4 and Daniels2/4.

The saved roster-scoped CSV check passed previously, but its 14:23:27UTC temporary clearance can expire. This research does not renew it or certify final active status. Final inactives remain separate. Sum of means is an expected-score comparison, not joint upside or win probability. No actual Monday outcomes or synthetic target boosts were used.

## Supported next improvement

First reconcile final authoritative injury designations with stale native-Q values through the supported availability pipeline, retaining the original source and user policy. Separately label last-observed cross-season workload windows explicitly; do not advertise them as recent current-season opportunity or infer role expansion. Neither issue warrants automatically raising Watkins or selecting a narrative alternative. No operational code was changed in this audit. Evidence files: watkins_target_evidence.json, watkins_all_seasons.json, comparison.json. Research-only checks: salary/uniqueness assertions and exact highest-mean control reproduction passed; no application tests or new optimizer runs were executed.
