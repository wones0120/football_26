# Showdown selection regret and portfolio diversity audit



Research only · October 9, 2026 · no production behavior changed



## 1. Executive summary



Week 5 was an observed **deterministic selection miss within the saved pool**, not an absence of a substantially better generated roster. The pool contained 120.84, while its four actual deterministic selections topped out at 89.54 (31.30 regret). The best roster survived packet quality eligibility and was present in the complete AI Review Universe, but absent from the 20 v2 packet finalists. Actual AI attention and selection cannot be recovered from an immutable record.

A generic top10 ceiling-outsider expansion would have surfaced rank41 with ten additional reviews; top3/5/8 would not. The attention expansion alone did not improve the fixed objective selection proxy. The two observed Week5 rosters had different captains and thesis labels but shared five physical players, the same quarterback, and most football exposure. Four-player-overlap alternatives preserved >=95% of both mean and ceiling; three-player-overlap alternatives could preserve >=90%, but not >=95%. Neither cap is justified as a production rule by these results.

Only Week4 Thursday and Week5 Thursday are usable prelock-input replays. Week4 Sunday was generated after kickoff and remains descriptive. This is two usable slates, not three-slate statistical validation.



## 2. Data/time-safety methodology



The isolated research runner reads only saved source snapshots and packet candidates during `freeze`. It verifies the original candidate-pool hash, preserves every variant rank, resolves six canonical physical-player IDs plus CPT identity, and saves all attention-set IDs and pair-policy IDs. Only after writing and hashing that freeze does `export-outcomes` open a read-only database transaction for actuals, fields and exact entries. `evaluate` verifies code/source/packet/pair hashes before reading labels. The reporter joins evaluation outcomes to already frozen IDs and writes a separate all-pairs evaluation artifact.

No solver or candidate generation runs in the replay. Packet quality eligibility remains the saved v2 rule: both fractions >=0.80 and either fraction >=0.90 or archived selector top3. Original production variant quality flags are retained separately; they are not silently equated with packet eligibility. P90 means summed marginal P90 proxy, not a calibrated lineup P90. Mean and ceiling are saved baseline metrics, independent of scenario-conditioned objective scores.

Canonical joins use UUID player identity, captain identity and saved variant maps. Field construction resolves contest+slot through existing native salary-backed canonical aliases; unresolved field rosters stay unavailable. Actual CPT observations are divided by 1.5 to establish base points, then multiplied exactly once when scoring. Conflicting/missing actuals are not zero-imputed. DK score comparisons use two decimals to remove float32 export noise; competition ranks and boundary ties are reported per contest. Contest samples are not pooled as independent slates.

Chronology caveat: earlier learning reports marked chronology unavailable because `games_represented` kickoff evidence was missing. This audit additionally uses the saved selected-player `game_id` kickoff, source cutoff, run creation, and persisted lineup timestamps. Thursday sources precede kickoff; Sunday does not. Packets and classifier annotations were serialized after kickoff, so this audit does not certify contemporaneous packet download or immutable historical AI judgment. Prior user-supplied Week5 outcomes and prior research were already known; this is a fixed retrospective parameter grid, not an outcome-blind experiment. No policy was changed after its outcome join.

Freeze SHA-256: `ea550288cd56d6fb0c9e64fceef0238bf3a2d07ec97cacc5df2ba05b4cc7b234`. Selected IDs, exact formulas, source/packet/pair hashes, and event clocks: `artifacts/showdown_selection_diversity_audit/prelock_policy_freeze.json`. Actual recorded AI selection and considered-set records: none found in repository JSON artifacts or available database records; **unknown**, not assumed absent historically.



## 3. Historical slate availability



| Slate | Created / cutoff (ET) | Kickoff (ET) | Replay | Variants / distinct / eligible / finalists |
| --- | --- | --- | --- | --- |
| W4 THURSDAY_NIGHT | 2026-10-01T15:08:58.102354-04:00 / 2026-10-01T11:07:44.570069-04:00 | 2026-10-01T20:15:00-04:00 | available | 149 / 117 / 93 / 20 |
| W4 SUNDAY_NIGHT | 2026-10-04T22:08:01.011956-04:00 / 2026-10-04T18:07:00.375627-04:00 | 2026-10-04T20:20:00-04:00 | unavailable: postkickoff generation | 131 / 110 / 110 / 20 |
| W5 THURSDAY_NIGHT | 2026-10-08T11:48:49.974980-04:00 / 2026-10-08T07:47:52.246664-04:00 | 2026-10-08T20:15:00-04:00 | available | 131 / 102 / 75 / 20 |

Complete loaded/scored contest fields exist for all 11 contests. Saved actual entry evidence exists for all slates. A saved field or report does not repair late generation chronology.



## 4. Week 4 Thursday



Run `ffb8acf8-2e31-414e-81da-417d6d82c584`; **prelock_saved_run**. Saved variants/distinct/eligible/finalists: 149/117/93/20.

Generated 114.96 → eligible 114.96 → considered **unknown** → deterministic-selected 106.73 → run-linked-entered 106.73. All observed entered best: 106.73. Recorded AI/manual selected set: **unknown**.

Eventual best archived selector rank 72; eligible **yes**, v2 packet finalist **no**, full universe **yes**. Deterministic regret 8.23; finalist attention potential gap 3.53.



| Attention group | Count | Best actual |
| --- | --- | --- |
| HIGH_market | 21 | 114.46 |
| complete_ai_review_universe | 93 | 114.96 |
| deterministic_packet_finalists | 20 | 111.43 |
| high_ceiling_nonfinalists_095 | 15 | 102.78 |
| highest_mean | 1 | 98.02 |
| highest_p90 | 1 | 94.42 |
| nonfinalist_quality_eligible | 73 | 114.96 |
| selector_top10 | 10 | 112.73 |
| selector_top20 | 20 | 112.73 |



| Contest | Entries | Winner | Top1% cutoff | Top5% cutoff | Generated top10% count/rate |
| --- | --- | --- | --- | --- | --- |
| 196187076 | 99088 | 120.74 | 112.08 | 106.66 | 21/17.9% |
| 196187096 | 5945 | 120.74 | 112.08 | 106.73 | 22/18.8% |
| 196187097 | 5945 | 120.74 | 112.08 | 106.74 | 22/18.8% |
| 196272912 | 2378 | 120.74 | 112.08 | 104.78 | 24/20.5% |



Exact entered records: 6; distinct rosters 3; repeated roster entries across contests 3. True execution regret is unknown; the diagnostic selected-to-run-linked-entry gap is 0.00.



No tested ceiling attention rule surfaced its rank72 eventual best. The best finalist scored 111.43 versus 114.96 generated, a 3.53 potential attention loss. The actual production portfolio topped out at 106.73; these sets are different and must not be conflated. The top-two objective proxy scored 111.43 and already shared only four players.



## 5. Week 4 Sunday



Run `dc21b3ab-c330-487c-bb88-766f9a71f04c`; **retrospective_unverified_generation**. Saved variants/distinct/eligible/finalists: 131/110/110/20.

Generated 167.04 → eligible 167.04 → considered **unknown** → deterministic-selected 111.37 → run-linked-entered 111.37. All observed entered best: 111.37. Recorded AI/manual selected set: **unknown**.

Eventual best archived selector rank 43; eligible **yes**, v2 packet finalist **no**, full universe **yes**. Deterministic regret 55.67; finalist attention potential gap 18.97.



| Attention group | Count | Best actual |
| --- | --- | --- |
| HIGH_market | 78 | 167.04 |
| complete_ai_review_universe | 110 | 167.04 |
| deterministic_packet_finalists | 20 | 148.07 |
| high_ceiling_nonfinalists_095 | 59 | 164.74 |
| highest_mean | 1 | 111.37 |
| highest_p90 | 1 | 111.37 |
| nonfinalist_quality_eligible | 90 | 167.04 |
| selector_top10 | 10 | 116.44 |
| selector_top20 | 20 | 116.44 |



| Contest | Entries | Winner | Top1% cutoff | Top5% cutoff | Generated top10% count/rate |
| --- | --- | --- | --- | --- | --- |
| 196285052 | 47562 | 175.06 | 163.33 | 151.86 | 12/10.9% |
| 196285061 | 3567 | 175.06 | 165.28 | 152.56 | 12/10.9% |
| 196285072 | 3963 | 174.14 | 160.06 | 148.66 | 12/10.9% |
| 196285073 | 4756 | 173.96 | 160.94 | 148.66 | 12/10.9% |



Exact entered records: 12; distinct rosters 5; repeated roster entries across contests 7. True execution regret is unknown; the diagnostic selected-to-run-linked-entry gap is 0.00.



Run creation and lineup persistence at 22:08 ET followed 20:20 kickoff, despite an 18:07 input cutoff. Therefore no attention or pair replay selection is fabricated for this slate. Its rank43 best, 167.04 versus 111.37 selected, is descriptive only. It cannot establish a prelock opportunity, validate an AI policy, or contribute to cross-slate improvement averages.



## 6. Week 5 Thursday



Run `3a41af88-a28c-41b1-888c-462ddcd7d74d`; **prelock_saved_run**. Saved variants/distinct/eligible/finalists: 131/102/75/20.

Generated 120.84 → eligible 120.84 → considered **unknown** → deterministic-selected 89.54 → run-linked-entered 86.36. All observed entered best: 89.79. Recorded AI/manual selected set: **unknown**.

Eventual best archived selector rank 41; eligible **yes**, v2 packet finalist **no**, full universe **yes**. Deterministic regret 31.30; finalist attention potential gap 22.90.



| Attention group | Count | Best actual |
| --- | --- | --- |
| HIGH_market | 43 | 120.84 |
| complete_ai_review_universe | 75 | 120.84 |
| deterministic_packet_finalists | 20 | 97.94 |
| high_ceiling_nonfinalists_095 | 19 | 120.84 |
| highest_mean | 1 | 86.36 |
| highest_p90 | 1 | 86.36 |
| nonfinalist_quality_eligible | 55 | 120.84 |
| selector_top10 | 10 | 80.99 |
| selector_top20 | 20 | 87.49 |



| Contest | Entries | Winner | Top1% cutoff | Top5% cutoff | Generated top10% count/rate |
| --- | --- | --- | --- | --- | --- |
| 196438552 | 118906 | 136.59 | 126.64 | 113.89 | 4/3.9% |
| 196438575 | 5945 | 134.84 | 130.00 | 113.49 | 4/3.9% |
| 196438576 | 8917 | 134.84 | 124.50 | 111.60 | 4/3.9% |



Exact entered records: 3; distinct rosters 2; repeated roster entries across contests 1. True execution regret is unknown; the diagnostic selected-to-run-linked-entry gap is 3.18.



The largest contest winner scored 136.59; saved-pool best was 15.75 lower, 5.80 below the top1% cutoff and 6.95 above the top5% cutoff. Generation therefore retained an important improvement over selections without reaching the field winner. Only four of 102 generated distinct rosters reached the top10% score band in each loaded contest.

The actual four deterministic selections were archived ranks 3,26,42,44. The observed entries were two copies of the Dak roster (rank42, 86.36) in different contests and one Bucky roster (rank56, 89.79). Both exact canonical rosters exist in the frozen generated pool. Rank56 was not deterministic-selected and lacks a saved run-selection link; this does not imply missing generation. The best run-linked entry is 86.36, producing a 3.18 diagnostic gap to the run's best selected 89.54. The best observed entry is 89.79, but subtracting it from 89.54 would conflate a generated non-selected roster with the deterministic selected set. True AI/manual execution regret remains unknown.



### Candidate `3a41af88-a28c-41b1-888c-462ddcd7d74d:41`: prelock trace



Canonical candidate ID `3a41af88-a28c-41b1-888c-462ddcd7d74d:dee93250fc131f45`; rank alias `:41`; distinct-pool selector rank 33; ceiling rank 17. Mean 83.20 (0.8898); summed P90 155.68 (0.9636); objective 171.97; salary 49100, left 900.

Roster: Cade Otton FLEX, Dak Prescott FLEX, George Pickens FLEX, Ryan Flournoy CPT, Javonte Williams FLEX, Bucky Irving FLEX.

Quality eligible (`ceiling_within_strong_tolerance`); not finalist; full universe visible. Captain Ryan Flournoy, favorite-side WR. Team split 4-2 DAL; QB favorite_qb_only; primary thesis `favorite_pass_win|WR|4-2_favorite|favorite_qb_only`; all scenarios favorite_pass_win; market HIGH (`favorite_win_aligned_with_saved_spread`); risk `very_low_projected_flex_ownership`. Role-specific ownership is partial: FLEX sum 107.26; captain/total ownership unavailable.

Prelock detectability, without using its actual score: it is **ninth** among eligible nonfinalists by ceiling. Top10 adds eight ahead and one alongside it; the attention set becomes 30 candidates. The 0.95 band (with or without market screen) adds 19, for 39 total; top3/5/8 and 0.97/0.99 do not surface it. Its captain/script combination already has 1 finalists, and the differentiated-top5 rule misses it. Strong ceiling, aligned market and acceptable mean make it rational to inspect under a generic top10 policy; it is not an obvious top-three ceiling outsider or a uniquely novel football family. No Flournoy-specific rule is needed. This does not prove an AI should have picked it.



## 7. Candidate-generation findings



Best generated and best packet-eligible actuals are equal on all three descriptive pools; quality eligibility did not remove the eventual best. Week4 Thursday reaches top1% score thresholds, Week5 reaches top5% but not top1%, and Sunday reaches top1% descriptively. The field-winner gaps coexist with much larger downstream selection gaps. They do not isolate a generator defect or justify changing generation.



## 8. High-ceiling non-finalist attention findings



The following are frozen **attention sets**, not selected AI portfolios. `Best visible` is postgame potential coverage. `Proxy best` evaluates a separately frozen top-two objective choice; it is not oracle selection.



| Slate | Policy | Added / total | Best generated visible? | Best visible | Proxy best |
| --- | --- | --- | --- | --- | --- |
| W4 Thu | A_finalists | 0 / 20 | no | 111.43 | 111.43 |
| W4 Thu | B_top10 | 10 / 30 | no | 111.43 | 111.43 |
| W4 Thu | B_top3 | 3 / 23 | no | 111.43 | 111.43 |
| W4 Thu | B_top5 | 5 / 25 | no | 111.43 | 111.43 |
| W4 Thu | B_top8 | 8 / 28 | no | 111.43 | 111.43 |
| W4 Thu | C_0.95 | 15 / 35 | no | 111.43 | 111.43 |
| W4 Thu | C_0.97 | 4 / 24 | no | 111.43 | 111.43 |
| W4 Thu | C_0.99 | 0 / 20 | no | 111.43 | 111.43 |
| W4 Thu | D_0.95 | 13 / 33 | no | 111.43 | 111.43 |
| W4 Thu | D_0.97 | 4 / 24 | no | 111.43 | 111.43 |
| W4 Thu | D_0.99 | 0 / 20 | no | 111.43 | 111.43 |
| W4 Thu | E_differentiated_top5 | 5 / 25 | no | 111.43 | 111.43 |
| W5 Thu | A_finalists | 0 / 20 | no | 97.94 | 80.99 |
| W5 Thu | B_top10 | 10 / 30 | yes | 120.84 | 80.99 |
| W5 Thu | B_top3 | 3 / 23 | no | 100.36 | 80.99 |
| W5 Thu | B_top5 | 5 / 25 | no | 100.36 | 80.99 |
| W5 Thu | B_top8 | 8 / 28 | no | 100.36 | 80.99 |
| W5 Thu | C_0.95 | 19 / 39 | yes | 120.84 | 80.99 |
| W5 Thu | C_0.97 | 3 / 23 | no | 100.36 | 80.99 |
| W5 Thu | C_0.99 | 0 / 20 | no | 97.94 | 80.99 |
| W5 Thu | D_0.95 | 19 / 39 | yes | 120.84 | 80.99 |
| W5 Thu | D_0.97 | 3 / 23 | no | 100.36 | 80.99 |
| W5 Thu | D_0.99 | 0 / 20 | no | 97.94 | 80.99 |
| W5 Thu | E_differentiated_top5 | 5 / 25 | no | 97.94 | 80.99 |

B uses ceiling order with rank/ID tie breaks. C adds all eligible outsiders above the threshold. D additionally requires MEDIUM/HIGH market compatibility. E adds at most five eligible >=0.95-ceiling outsiders whose captain/script combination or primary thesis has at most one finalist. These definitions and all candidate IDs are serialized verbatim. No thresholds or weights were fit to actuals. Coverage cannot decrease when sets only expand; the relevant empirical question is how much useful coverage each review budget adds.



## 9. Deterministic finalist coverage



| Slate | Best generated rank | Best finalist actual | Potential coverage loss | Chronology |
| --- | --- | --- | --- | --- |
| W4 THURSDAY_NIGHT | 72 | 111.43 | 3.53 | prelock_saved_run |
| W4 SUNDAY_NIGHT | 43 | 148.07 | 18.97 | retrospective_unverified_generation |
| W5 THURSDAY_NIGHT | 41 | 97.94 | 22.90 | prelock_saved_run |

Finalists omit the best saved roster in both usable replays; Sunday shows the same pattern descriptively. A compact finalist set inevitably omits candidates. These observations support testing an attention supplement, not labeling the production selector defective or replacing finalist policy.



## 10. AI Review Universe coverage



The full saved/reconstructed v2 review universes contain 93,110,75 eligible candidates for Thursday W4, Sunday W4, Thursday W5 respectively. Each contains the eventual best generated roster. These are universe-availability statements from frozen-input packet reconstruction, not evidence that the AI read every candidate. `best considered`, recorded AI picks, rejected IDs and reasoning remain unknown. Prospectively store them.



## 11. Player-core overlap analysis



| Slate | Eligible pairs | 0–2 | 3 | 4 | 5 | 6 physical | Different CPT + five shared |
| --- | --- | --- | --- | --- | --- | --- | --- |
| W4 THURSDAY_NIGHT | 4278 | 418 | 1574 | 1720 | 513 | 53 | 419 |
| W4 SUNDAY_NIGHT | 5995 | 731 | 2650 | 2097 | 507 | 10 | 393 |
| W5 THURSDAY_NIGHT | 2775 | 272 | 947 | 1108 | 418 | 30 | 343 |

`shared_player_count` counts physical UUIDs independent of CPT/FLEX. `unique_players_across_pair = 12 - shared_player_count`. Six shared with different captains is the same physical roster with different scoring emphasis, not an exact duplicate lineup. Exact duplicates are removed by captain+six-player identity; duplicate entries remain an execution diagnostic.



| Week5 observed-pair dimension | Diagnostic |
| --- | --- |
| Captain | Different: Dak (QB, DAL/favorite) and Bucky (RB, TB/underdog) |
| Thesis | Different saved structural labels; full signatures and scenario overlap in JSON |
| Physical player core | 5/6 shared; 7 total unique; high player-core overlap |
| Shared FLEX | 3 (captains swap slots) |
| Team split | Different: Dak DAL4/TB2; Bucky DAL3/TB3 |
| QB structure | Same: Dak only / favorite_qb_only |
| Shared physical exposure | Dak, CeeDee, Bucky, Aubrey, Otton |
| Only differing physical players | Ryan Flournoy versus Chase McLaughlin |

These were meaningfully different captain-weighting and team-split bets, but diversification of the physical player core was limited. Describing them simply as two distinct script bets overstated the exposure spread. This conclusion follows from prelock roster identities, not CeeDee's miss or Bucky's spike. High overlap is a diagnostic, not an automatic verdict of poor selection.



## 12. Two-entry portfolio experiments



Control maximizes the pair's saved objective sum, without pretending to reproduce production exposure/scenario constraints or AI reasoning. A requires different captains. B tests different archetypes and different primary football scenarios separately. C/D cap shared players. E uses average normalized quality plus a predeclared complementarity coefficient; 0 is its own quality-only baseline and differs from objective control.



| Slate | Policy | Archived ranks | Shared | Min mean / P90 | Best / avg actual |
| --- | --- | --- | --- | --- | --- |
| W4 Thu | A_different_captains | 2, 1 | 4 | 0.9278 / 0.9554 | 111.43 / 102.40 |
| W4 Thu | B_different_archetypes | 11, 1 | 6 | 0.9301 / 0.9707 | 94.38 / 93.88 |
| W4 Thu | B_different_scripts | 2, 1 | 4 | 0.9278 / 0.9554 | 111.43 / 102.40 |
| W4 Thu | C_shared_le4 | 2, 1 | 4 | 0.9278 / 0.9554 | 111.43 / 102.40 |
| W4 Thu | D_shared_le3 | 3, 1 | 3 | 0.9301 / 0.9471 | 106.73 / 100.05 |
| W4 Thu | E_lambda_0.00 | 71, 28 | 5 | 0.9783 / 0.9785 | 101.12 / 97.77 |
| W4 Thu | E_lambda_0.01 | 71, 28 | 5 | 0.9783 / 0.9785 | 101.12 / 97.77 |
| W4 Thu | E_lambda_0.05 | 71, 28 | 5 | 0.9783 / 0.9785 | 101.12 / 97.77 |
| W4 Thu | E_lambda_0.10 | 71, 28 | 5 | 0.9783 / 0.9785 | 101.12 / 97.77 |
| W4 Thu | control | 2, 1 | 4 | 0.9278 / 0.9554 | 111.43 / 102.40 |
| W5 Thu | A_different_captains | 26, 1 | 4 | 0.9550 / 0.9650 | 89.54 / 85.27 |
| W5 Thu | B_different_archetypes | 42, 1 | 5 | 0.9705 / 0.9892 | 86.36 / 83.67 |
| W5 Thu | B_different_scripts | 5, 1 | 4 | 0.8963 / 0.9548 | 80.99 / 67.34 |
| W5 Thu | C_shared_le4 | 5, 1 | 4 | 0.8963 / 0.9548 | 80.99 / 67.34 |
| W5 Thu | D_shared_le3 | 8, 1 | 3 | 0.9255 / 0.9529 | 80.99 / 63.84 |
| W5 Thu | E_lambda_0.00 | 42, 44 | 5 | 0.9820 / 0.9896 | 88.36 / 87.36 |
| W5 Thu | E_lambda_0.01 | 42, 44 | 5 | 0.9820 / 0.9896 | 88.36 / 87.36 |
| W5 Thu | E_lambda_0.05 | 42, 1 | 5 | 0.9705 / 0.9892 | 86.36 / 83.67 |
| W5 Thu | E_lambda_0.10 | 42, 1 | 5 | 0.9705 / 0.9892 | 86.36 / 83.67 |
| W5 Thu | control | 4, 1 | 5 | 0.9230 / 0.9703 | 80.99 / 80.39 |

A different-archetype pair can still share all six players (Week4 Thursday), demonstrating why captain labels cannot substitute for physical overlap. Week5 different-captain control improves proxy best by 8.55; <=4 and <=3 controls do not improve its best. Week4 <=3 reduces best by 4.70. E's soft parameter sweep keeps five-player cores in both slates and provides no reliable outcome benefit. Every result remains a fixed counterfactual proxy.



## 13. Quality cost of diversification



Each row below freezes a pair by maximizing its minimum of all four mean/ceiling fractions, with average-quality and ID tie breaks. It is not the best pair chosen by actual score. Counts show how many pairs meet both lineups' quality bands.



| Slate | Overlap cap | All pairs | Best joint min mean / P90 | Highest possible min P90 | Joint95 / joint90 pairs |
| --- | --- | --- | --- | --- | --- |
| W4 Thu | 2 | 418 | 0.9596 / 0.9255 | 0.9374 | 0 / 185 |
| W4 Thu | 3 | 1992 | 0.9697 / 0.9488 | 0.9580 | 0 / 1087 |
| W4 Thu | 4 | 3712 | 0.9783 / 0.9609 | 0.9785 | 30 / 2152 |
| W4 Thu | 5 | 4225 | 0.9783 / 0.9785 | 0.9850 | 48 / 2508 |
| W5 Thu | 2 | 272 | 0.9256 / 0.9540 | 0.9540 | 0 / 21 |
| W5 Thu | 3 | 1219 | 0.9423 / 0.9398 | 0.9758 | 0 / 225 |
| W5 Thu | 4 | 2327 | 0.9808 / 0.9782 | 0.9811 | 14 / 671 |
| W5 Thu | 5 | 2745 | 0.9820 / 0.9896 | 0.9896 | 41 / 924 |

Week5 <=4 can retain minimum mean 0.9808 and P90 0.9782, with 14 joint95 pairs. <=3 retains minimum mean 0.9423 and P90 0.9398 at the best balanced pair, with 225 joint90 pairs. Week4 Thursday <=4 has 30 joint95 pairs; <=3 has 1,087 joint90 pairs and zero joint95. Thus reducing five to four need not sacrifice most prelock quality. Three is more expensive against a joint95 standard, but not demonstrated universally too restrictive. Pure objective-maximizing capped policies do not necessarily choose these balanced-quality alternatives; their explicit opportunity costs are in JSON.

| Slate | Overlap cap | Best joint-quality pair actual best / average | Best objective pair joint95 / joint90 actual best |
| --- | --- | --- | --- |
| W4 Thu | 2 | 98.02 / 96.42 | unknown / 93.37 |
| W4 Thu | 3 | 101.12 / 97.28 | unknown / 106.73 |
| W4 Thu | 4 | 101.12 / 95.22 | 99.77 / 111.43 |
| W4 Thu | 5 | 101.12 / 97.77 | 94.42 / 111.43 |
| W5 Thu | 2 | 74.79 / 72.39 | unknown / 73.39 |
| W5 Thu | 3 | 84.86 / 78.88 | unknown / 80.99 |
| W5 Thu | 4 | 86.36 / 85.61 | 89.54 / 80.99 |
| W5 Thu | 5 | 88.36 / 87.36 | 89.54 / 80.99 |

These quality-preserving selections also have mixed eventual outcomes: best-joint-quality <=4 is neutral versus <=5 on Week4 Thursday and lower by 2.00 on Week5; <=3 is neutral on Week4 and lower by 3.50 on Week5. The joint95 objective arm improves Week4 under <=4, while Week5 is neutral. Quality feasibility is clear; outcome superiority is not. None of these pairs was selected on actual scores.

### Postgame field-construction context



Complete-field context is evaluated after freezing, separately per contest and top1/5/10%/whole-field bands. JSON includes team-split frequencies, captain IDs/positions, actual role ownership, salary-left mean/median/range/buckets and counts of players below 10% actual role ownership. These frequencies never enter selection. Field resolution failures are counted; descriptive salary metrics require all six saved salaries.



| Week5 contest | Band | Resolved entries | 3–3 share | Top two CPT counts | Mean salary left |
| --- | --- | --- | --- | --- | --- |
| 196438552 | top1% | 1197 | 70.7% | George Pickens 714, Bucky Irving 461 | 528.63 |
| 196438552 | top5% | 5988 | 46.0% | George Pickens 2790, Bucky Irving 1584 | 652.99 |
| 196438552 | top10% | 11911 | 42.8% | George Pickens 4722, Bucky Irving 2496 | 616.02 |
| 196438552 | top100% | 118508 | 28.3% | CeeDee Lamb 21518, Dak Prescott 19043 | 658.48 |
| 196438575 | top1% | 65 | 84.6% | George Pickens 52, Bucky Irving 13 | 384.62 |
| 196438575 | top5% | 301 | 56.1% | George Pickens 150, Bucky Irving 68 | 519.60 |
| 196438575 | top10% | 598 | 42.6% | George Pickens 283, Bucky Irving 101 | 509.73 |
| 196438575 | top100% | 5928 | 28.6% | Dak Prescott 1112, CeeDee Lamb 1002 | 538.08 |
| 196438576 | top1% | 92 | 69.6% | George Pickens 57, Bucky Irving 26 | 441.30 |
| 196438576 | top5% | 482 | 42.7% | George Pickens 239, Bucky Irving 101 | 521.99 |
| 196438576 | top10% | 893 | 42.8% | George Pickens 342, Bucky Irving 161 | 533.97 |
| 196438576 | top100% | 8871 | 26.9% | Dak Prescott 1650, CeeDee Lamb 1551 | 539.04 |

The top-field 3–3 pattern is postgame context, not a replay input or a proposed team-split rule. Actual ownership is distinct from saved projected ownership, which is partial/unavailable for many rosters.



## 14. Selection-regret attribution



| Stage | Week4 Thursday | Week4 Sunday | Week5 Thursday |
| --- | --- | --- | --- |
| PLAYER_PROJECTION | Observed residuals contribute; one volatile outcome does not establish model defect. | Observed residuals contribute; one volatile outcome does not establish model defect. | Observed residuals contribute; one volatile outcome does not establish model defect. |
| CANDIDATE_GENERATION | Contained the best-known saved roster; field winner remains outside saved pool. Finite generation coverage gap is descriptive, not proof of defective generation. | Contained the best-known saved roster; field winner remains outside saved pool. Finite generation coverage gap is descriptive, not proof of defective generation. | Contained the best-known saved roster; field winner remains outside saved pool. Finite generation coverage gap is descriptive, not proof of defective generation. |
| QUALITY_ELIGIBILITY | No loss of best generated candidate under saved packet framework. | No loss of best generated candidate under saved packet framework. | No loss of best generated candidate under saved packet framework. |
| CANDIDATE_ATTENTION | Best generated candidate absent from saved v2 packet finalists and present in full AI Review Universe; actual considered set unknown. | Best generated candidate absent from saved v2 packet finalists and present in full AI Review Universe; actual considered set unknown. | Best generated candidate absent from saved v2 packet finalists and present in full AI Review Universe; actual considered set unknown. |
| FINAL_SELECTION | Observed deterministic pool-selection regret 8.23; actual AI/manual selection authority unknown. | Observed deterministic pool-selection regret 55.67; actual AI/manual selection authority unknown. | Observed deterministic pool-selection regret 31.30; actual AI/manual selection authority unknown. |
| PORTFOLIO_DIVERSIFICATION | All-pairs diagnostics available; no recorded two-entry selection rationale to attribute causation. | All-pairs diagnostics available; no recorded two-entry selection rationale to attribute causation. | Five shared physical players in Week5 observed pair restrict exposure spread; cap experiments do not establish outcome benefit. |
| ENTRY_EXECUTION | Exact entries known; duplicate rosters increase repeated exposure. Missing immutable manual selection prevents true execution-regret attribution. | Exact entries known; duplicate rosters increase repeated exposure. Missing immutable manual selection prevents true execution-regret attribution. | Exact entries known; duplicate rosters increase repeated exposure. Missing immutable manual selection prevents true execution-regret attribution. |



Week5 Bucky: saved baseline 12.23, actual base 34.50, residual +22.27. CeeDee: saved baseline 18.13, actual base 2.90, residual -15.23. These realized residuals help explain portfolio outcomes; they did not define diversity or policy screens. A generator that retained a better eventual roster does not eliminate projection uncertainty, and two player residuals do not establish a defective model.



## 15. Cross-slate findings



| Attention policy | Helped / neutral / hurt coverage | Average added | Mean coverage actual change | Mean proxy regret change |
| --- | --- | --- | --- | --- |
| A_finalists | 0/2/0 | 0.00 | 0.00 | 0.00 |
| B_top10 | 1/1/0 | 10.00 | 11.45 | 0.00 |
| B_top3 | 1/1/0 | 3.00 | 1.21 | 0.00 |
| B_top5 | 1/1/0 | 5.00 | 1.21 | 0.00 |
| B_top8 | 1/1/0 | 8.00 | 1.21 | 0.00 |
| C_0.95 | 1/1/0 | 17.00 | 11.45 | 0.00 |
| C_0.97 | 1/1/0 | 3.50 | 1.21 | 0.00 |
| C_0.99 | 0/2/0 | 0.00 | 0.00 | 0.00 |
| D_0.95 | 1/1/0 | 16.00 | 11.45 | 0.00 |
| D_0.97 | 1/1/0 | 3.50 | 1.21 | 0.00 |
| D_0.99 | 0/2/0 | 0.00 | 0.00 | 0.00 |
| E_differentiated_top5 | 0/2/0 | 5.00 | 0.00 | 0.00 |



| Pair policy | Helped / neutral / hurt best-entry | Mean actual change | Mean regret change |
| --- | --- | --- | --- |
| A_different_captains | 1/1/0 | 4.28 | -4.28 |
| B_different_archetypes | 1/0/1 | -5.84 | 5.84 |
| B_different_scripts | 0/2/0 | 0.00 | -0.00 |
| C_shared_le4 | 0/2/0 | 0.00 | -0.00 |
| D_shared_le3 | 0/1/1 | -2.35 | 2.35 |
| E_lambda_0.00 | 1/0/1 | -1.47 | 1.47 |
| E_lambda_0.01 | 1/0/1 | -1.47 | 1.47 |
| E_lambda_0.05 | 1/0/1 | -2.47 | 2.47 |
| E_lambda_0.10 | 1/0/1 | -2.47 | 2.47 |
| control | 0/2/0 | 0.00 | -0.00 |

Per-slate/per-contest best-entry percentile changes are in JSON. All attention proxy percentile changes are zero. <=4 pair-control percentile changes are zero on both usable slates. <=3 worsens Week4 Thursday and is neutral in Week5. These are paired descriptions of two slates with no statistical significance claim.



| Hypothesis | Evidence status |
| --- | --- |
| H1 | Ceiling outsiders improve coverage in Week5, not Week4 Thursday; expanded visibility did not change the fixed selection proxy. Sunday unavailable. |
| H2 | Confirmed diagnostic five-player core despite captain and thesis differences; insufficient diversification is an outcome-risk hypothesis, not established statistical fact. |
| H3 | <=4 high-quality alternatives existed on both usable slates. Pure objective-cap policies had neutral best-entry outcomes on both; prospective diagnostic/attention experiment justified, no hard rule supported. |
| H4 | <=3 eliminates the joint95 band on both slates but retains joint90 pairs; costly at a stringent standard, not proven universally too restrictive. |



## 16. What the evidence does NOT justify



It does not justify a production defect claim, historical AI-pick reconstruction, automatic low-overlap superiority, a new ceiling threshold, a new finalist policy, weight fitting, player-specific rules or exposure changes, a 3–3 rule, or projection retraining from this sample. Sunday cannot be rehabilitated by its prelock cutoff. Packet availability is not actual consideration, and a favorable outcome of one visible candidate is not proof of rational ex ante selection. The research controls also differ from production portfolio constraints and live manual choices.



## 17. Candidate hypotheses for future live testing



H1: a small ceiling-outsider supplement captures useful candidates at manageable review cost. H2: five shared physical players leave limited portfolio coverage despite captain/thesis differences. H3: reviewing <=4 alternatives can spread exposure while retaining strong mean and ceiling. H4: forcing <=3 is expensive enough that it should remain a shadow sensitivity arm. These are hypotheses; none is promoted.



## 18. Recommended next experiment



For upcoming chronologically valid Showdown slates, preregister a research-only shadow protocol before kickoff. Preserve production inputs and outputs. Save finalized source/pool/packet hashes, the existing finalist control and a top10 eligible-ceiling-outsider attention set (at most 30 total with current finalist size). Require the reviewer to record actual considered IDs, two chosen IDs, rejected alternatives, quality tradeoffs and any user-preference exclusions before lock. Capture selection time and exact submitted entries separately.

Before choosing two live entries, explicitly inspect shared physical-player count, shared FLEX, captain position/side, primary script, scenario overlap, team split, QB structure and available projected ownership. For any five-player core, inspect a <=4 alternative and its minimum mean/P90 cost; record a rationale if the higher-overlap pair remains preferred. Shadow-log <=3 without forcing it. Leave the existing optimizer behavior intact. Freeze all decisions before joining actuals, then compare best-entry capture, regret, review burden and execution fidelity across a larger cohort. Do not adjust the grid mid-cohort.



### KEEP



- Canonical identity, frozen pools, existing projection/mean/P90 calculations and quality framework.

- Complete AI Review Universe, stage separation and chronology exclusions.



### TEST PROSPECTIVELY



- Predeclare finalists plus top10 eligible ceiling outsiders as a shadow attention set; save actual considered and rejected IDs.

- Show shared physical-player count before two-entry selection; compare <=4 alternatives with explicit mean/ceiling opportunity cost, allowing justified exceptions.

- Keep <=3 as a shadow sensitivity arm; do not force it or tune complementarity weights.



### DO NOT CHANGE YET



- Production optimizer, candidate generation, finalist algorithm, quality thresholds, market compatibility, ownership, projections, salary or live AI Review Universe.

- No player-specific exposure changes, production overlap cap, fitted weights, or three-slate statistical claim.



## 19. Exact commands/tests used



The Week5 source was exported from `target.optimizer_run`, `target.lineup` and `target.lineup_player` in an explicit `SET TRANSACTION READ ONLY` transaction; Week4 uses previously saved exports. Week5 packet creation calls the unchanged `build_retrospective_packet` on that source with `ai_requested_entries=2`; this classifies saved candidates and does not run generation. Source export and packet artifacts are hashed by the freeze. Additional read-only chronology query: `SELECT optimizer_run_id, min(created_at), max(created_at) FROM target.lineup WHERE optimizer_run_id = ANY(:ids) GROUP BY optimizer_run_id`.

Initial capture/freeze/evaluation commands (completed before live classifier drift):

```bash
.venv/bin/python -m scripts.capture_showdown_selection_diversity_inputs
.venv/bin/python -m pytest tests/test_showdown_selection_diversity_audit.py -q
.venv/bin/python -m scripts.audit_showdown_selection_diversity freeze
.venv/bin/python -m scripts.audit_showdown_selection_diversity export-outcomes
.venv/bin/python -m scripts.audit_showdown_selection_diversity evaluate
.venv/bin/python -m scripts.report_showdown_selection_diversity
```

Concurrent work subsequently changed the live packet-classifier file. The original guard rejects that drift. Rerun this saved experiment from the hashed original packets and serialized annotations, without invoking the current classifier:

```bash
.venv/bin/python -m scripts.replay_saved_showdown_selection_diversity
.venv/bin/python -m scripts.report_showdown_selection_diversity
.venv/bin/python -m pytest tests/test_showdown_selection_diversity_audit.py -q
```

The offline verifier also checks the original freeze against its pre-outcome read manifest, every source/packet/pair hash, original policy code and definition hashes. The outcome extractor remains pinned to its before-audit hash. Only evidence verification changes to use frozen annotations; no ranking, candidate selection, policy definitions, thresholds or weights change.

The saved freeze is immutable: rerun `evaluate` and the reporter against the same freeze/outcome files. `freeze` refuses to overwrite it; a different grid must use a new artifact directory. Leakage tests poison nested candidates with actual points, ranks, field construction, ownership, hindsight and learning fields; mutation/hash tests fail closed; chronology tests reject late/equal/missing-zone clocks; identity tests cover slot-independent overlap, duplicate identity and single CPT scoring; infeasible constraints never silently relax. Additional reporting tests cover float32 score ties, evaluated-pair preservation and exact source/outcome linkage.

Audit-owned production edits: **none**. 197 existing backend runtime/UI files were compared to before-audit SHA-256s; global equality is **False** because concurrent work changed: `backend/app/product_schemas.py`, `backend/app/product_services/ai_showdown_packet.py`, `backend/app/product_services/optimizer.py`, `backend/app/product_services/showdown_qb_preferences.py`, `backend/app/api/product_routes.py`, `ui/src/App.tsx`, `ui/src/showdownReporting.ts`, `ui/src/RecentOptimizerRuns.tsx`, `ui/src/api.ts`, `ui/src/optimizerReport.ts`, `ui/src/research/ControlPlane.tsx`. Other observed existing-file changes: `backend/app/tests/product/overlap_ui_fixture.py`. This audit never edited those files and preserves them. Only isolated research scripts/tests/artifacts and documentation were added or updated by this audit. The original selection code and frozen packet/annotation data hashes still match the freeze; the current live annotation source differs and is not used in offline replay. No production rule was promoted.

Machine-readable deliverable: `SHOWDOWN_SELECTION_REGRET_AND_PORTFOLIO_DIVERSITY_AUDIT.json`; full prelock and evaluated pair features live in the referenced gzip artifacts. Report and JSON retain all requested unavailable/unknown stages explicitly.

Validation receipt and complete command results: `artifacts/showdown_selection_diversity_audit/validation_results.json`.
