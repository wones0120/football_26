# Classic expanded discovery multi-slate validation

Audit date: 2026-09-30; completed freeze/attachment: 2026-10-01 UTC. **One provisional historical experiment; zero exact-certified historical slates. Production unchanged.**

## 1. Executive summary

**SHADOW LONGER.** Expanded discovery finds substantial competitive coverage beyond the old pipeline in the recovered Week 3 case, but portfolio improvements are small and 400 is not established as the best default. Production remains unchanged at 205.

The local historical search is complete: 75 saved Sunday Main optimizer runs, 70 potentially relevant period labels and 40 historical season/week pairs were audited. **Exact-certified historical slates N=0; completed provisional historical experiments N=1 (2026 Week 3); chronological holdout N=0.** Week 4 remains a separate future-slate diagnostic. Refreshes do not increase the independent sample size.

A pre-lock September 25 backend archive allowed a 535-player Week 3 reconstruction and an unchanged 120-candidate legacy replay. It reproduced every saved selector score and 117/120 canonical rosters, but failed exact generation equivalence. The following historical experiment is therefore provisional throughout. Both saved and replayed old controls give the same recall and portfolio conclusions; 688 competitive rosters are missing from both controls. This is meaningful evidence of a generation limitation, not a certified multi-slate generalization result.

All discovery sources, four admissions from one preserved raw universe, the user's fixed five, and both dynamic thesis shadows were executed and frozen before actuals were loaded. No weights, correlation, ownership, projection, risk, exposure, overlap, distinct-QB or thesis parameters were tuned. The report completes the analysis possible from local evidence; the requested exact-certified multi-slate validation cannot be completed from the surviving historical provenance.

## 2. Slate cohort

| Slate | Date* | Stored games* | Saved eligible max* | Ownership players* | Market games* | Actual availability* | Contests / scored rows* | Pregame / postgame / field qualifies | Exclusion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024 W16 | 2024-12-22 | 11 | unknown | absent | 11 | fact:763 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2024 W17 | 2024-12-29 | 8 | unknown | absent | 8 | fact:762 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2024 W20 | 2025-01-19 | 4 | unknown | absent | 1 | fact:200 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W1 | 2025-09-07 | 12 | unknown | absent | 12 | fact:742 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W5 | 2025-10-05 | 10 | unknown | absent | 10 | fact:606 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W6 | 2025-10-12 | 10 | unknown | absent | 10 | fact:569 / contest:0 | 1 / 161764 | No / No / No | no frozen small-field control |
| 2025 W7 | 2025-10-19 | 10 | unknown | absent | 10 | fact:621 / contest:0 | 1 / 148632 | No / No / No | no frozen small-field control |
| 2025 W8 | 2025-10-26 | 10 | unknown | absent | 10 | fact:566 / contest:0 | 1 / 277447 | No / No / No | no frozen small-field control |
| 2025 W9 | 2025-11-02 | 11 | unknown | absent | 11 | fact:645 / contest:0 | 1 / 277447 | No / No / No | no frozen small-field control |
| 2025 W10 | 2025-11-09 | 10 | unknown | absent | 10 | fact:616 / contest:0 | 1 / 266594 | No / No / No | no frozen small-field control |
| 2025 W11 | 2025-11-16 | 11 | unknown | absent | 11 | fact:643 / contest:0 | 1 / 237812 | No / No / No | no frozen small-field control |
| 2025 W12 | 2025-11-23 | 11 | unknown | absent | 11 | fact:604 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W13 | 2025-11-30 | 10 | unknown | absent | 10 | fact:680 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W17 | 2025-12-28 | 9 | unknown | absent | 9 | fact:679 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2025 W18 | 2026-01-04 | 13 | unknown | absent | 13 | fact:691 / contest:0 | 0 / 0 | No / No / No | no frozen small-field control |
| 2026 W1 | 2026-09-13 | 12 | unknown | absent | 12 | fact:0 / contest:638 | 2 / 841537 | No / No / No | no frozen small-field control |
| 2026 W2 | 2026-09-20 | 13 | 359 | 523 | 13 | fact:0 / contest:0 | 0 / 0 | No / No / No | incomplete generation state |
| 2026 W3 | 2026-09-27 | 13 | 535 | 651 | 13 | fact:0 / contest:371 | 3 / 41616 | Provisional / Provisional / Provisional | exact old replay failed |
| 2026 W4 | 2026-10-04 | 12 | 471 | 601 | 0 | fact:0 / contest:0 | 0 / 0 | No / No / No | future; diagnostic only |

*Availability inventory only: dates come from Sunday daytime schedule headers; stored game counts are salary-table labels, not certified slate membership. Eligible counts are maxima over completed saved runs, including refreshes; the diagnostic Week 4 frame itself has 466 players, not the inventory maximum of 471. Ownership and market presence do not establish pre-lock availability. Fact actual counts are week-wide; contest counts use resolved canonical IDs. Counts do not prove complete scoring or representative field coverage. The initial inventory read availability counts only; actual score values were attached after the Week 3 pregame freeze.

The remaining 51 candidate period labels are listed individually with exclusion reasons in [cohort_audit_final.json](/Users/wones/git/football_26/artifacts/classic_discovery_multi_slate/cohort_audit_final.json). They include 2024 DEFAULT weeks 4–13, 15–17, 19–20 and 2025 DEFAULT weeks 1–22, plus MAIN/NORMAL/SUNDAY/SUNDAY_ALL aliases. They are excluded for uncertified Sunday Main membership, no original completed small-field control, and absent complete frozen generation inputs. DEFAULT projections were created in June/July 2026 for past seasons; creation after lock alone does not prove leakage, but no certified training/source cutoff and original small-field control survive for these periods. Week 20 stored MAIN membership also mixes postseason games and cannot be assumed to be a standard Sunday daytime Main slate.

Another 69 period labels are explicitly listed in `outside_scope` (Thursday, Monday, Sunday Late/Night, early-only, and other non-Main labels). A misleading Week 3 THURSDAY_NIGHT salary label contains multiple games; it was not silently repaired into a certified historical Main slate. The actual saved Sunday Main optimizer runs were examined independently.

The full 75-run field/key inventory is [run_inventory_detail.json](/Users/wones/git/football_26/artifacts/classic_discovery_multi_slate/run_inventory_detail.json). Every completed Week 2 small-field run (14) and Week 3 run (16) lacks both full generation and solver snapshots; their failed runs do not supply valid control universes. Week 1 has baseline/head-to-head/large-GPP runs, but no small-field control. The five 2025 Week 11 runs were created in 2026 and are not contemporaneous small-field controls.

The source audit examined all 30 completed Week 2/3 small-field runs again: **12 Week 2 and 16 Week 3 runs preceded lock; two Week 2 runs followed lock**. The separate [source reconstruction audit](/Users/wones/git/football_26/artifacts/classic_discovery_multi_slate/continuation_reconstruction_audit.json) records every run, frozen-field presence, saved generation metadata and source checks. These are 28 refreshes across two slates, not 28 independent slates. Exclusion is not based merely on the absence of the newer snapshot contract.

## 3. Chronology/leakage controls

The catalog/source queries used REPEATABLE READ, READ ONLY transactions. The original cohort audit timestamp is `2026-09-30T15:50:06.818905-04:00`; its canonical payload SHA-256 is `a6b688e867d5031a3b3aa8cbdff5fc3b0a2389b6cd2397069334badc01ce06d1`. Availability counts never selected inputs.

The recovered Codex checkpoint's tree/ref epoch is `2026-09-25T21:32:56.411Z`, before September 27 lock. It is not a commit timestamp or proof of the exact original solver environment. The control is `a6d7f5e7-db0f-44ae-87c4-60a826973408`, created September 25 at 21:25:39 EDT. Its 535 pinned projection/features were created at 08:46 EDT; salaries were restricted to canonical-ID records preceding the decision, with team/salary agreement for every player. Lagged role inputs include 403 importance records and 535 target inputs. Saved context adjustments and archived adapters were used. Partial ownership remains unavailable (522/535); missing numeric values follow the original zero conversion. Market values come from pinned features; explicit market observation provenance is absent.

Original modern injury/context observation stamps are missing for all 535. Historical eligibility was preserved, including 37 Q and one D legacy status; modern risk buckets remain unknown and an evidence gap is recorded. No current injury classification or added risk cap was substituted. This is an archived-policy experiment, not certification of modern availability safety. The Week 2 standalone role frame references a different projection run from its control and was not mixed into it. September 25 code cannot establish the original Week 2 generator.

All 120 saved selector scores match archived and current compact scoring exactly. Archived/current reconstructed mathematical models have identical objective, variables/bounds and constraint multiset: SHA-256 `b50562d7ab1e306d33ac2f67717b35710e307d5fbc10587bc09ca2643febf155`, 2,204 variables and 5,507 constraints. JSON-normalized historical configuration matches; a tuple/list representation difference in the raw replay diagnostic is not a config change. Nevertheless, exact generation failed: 117/120 rosters, 113/120 ordered positions. One alternative has an exact DST score tie; tie/no-good-cut cascades are plausible but not established for every difference. No settings were altered to force a match.

The complete pregame comparison was frozen at `2026-10-01T02:39:12.381642+00:00`, SHA-256 `5cc95e1364d3fdbed134aaf96bf369a24c576437088805f08b21731ba849352a`. Only then were actuals attached, at `2026-10-01T02:40:39.101564+00:00`. This is retrospective execution of reconstructed pre-lock inputs, not a claim the new experiment ran before lock. See the durable reconstruction, replay assessment, input/code hashes and pregame/postgame files in `artifacts/classic_discovery_multi_slate/week3_archived_control_check/`.

## 4. Old discovery architecture

The archived legacy generator ran unchanged: sequential 120 candidates, .35 mean/.48 ceiling/.17 correlation, leverage zero, templates QB+1/2 with bring-back 0/1, candidate uniqueness overlap 7, maximum two punts, original team/game limits 4/5, single TE, DST-opponent avoidance and Denver opponent exclusion. Original max exposure is 1.0 and aggregate caps are empty. These historical settings differ from Week 4's 205-candidate sharded baseline; neither control was homogenized.

The full archived replay took 1,611.98 seconds and returned 120 candidates. Three saved rosters were replaced by three alternatives; selector sum differs by only .002616. Saved and replayed controls are both retained. Exact qualification failed and remains failed; no repeated optimizer tuning or retries were used to manufacture equivalence.

## 5. Expanded architecture

The generalized Week 4 proposal was applied without outcome-dependent changes: global frontier; all 25 eligible QB directions; QB+1/+2/+3 with bring-back variants; bounded per-QB frontier enumeration; individual, double, triple and TE stack-partner sweeps; generic forced-player/player-gap probes across high mean/P90/role/value/ownership/environment and underrepresented players; RB/WR flex, DST salary tiers, balanced and stars/scrubs structures. TE flex is forbidden by the frozen single-TE policy.

There are 745 requests (one global plus 744 worker requests) and 1,822 solver events, using four workers, the existing 75-roster per-QB safety limit and .30 discovery window. The full deduplicated raw universe of 1,589 includes the union of both old controls (123 rosters), and is preserved without pruning. Targets 205/300/400/500 are admitted independently from this identical universe under the same frozen admission policy. No target receives additional discovery budget. Full requests, events, partitions, lineages, rosters and admissions remain in the frozen JSON and 744 cache files.

## 6. Per-slate frontier counts

| Tolerance | Week 3 known legal rosters | Count status |
| --- | --- | --- |
| 0.05 | 17 | exact |
| 0.10 | 206 | lower_bound |
| 0.15 | 494 | lower_bound |
| 0.20 | 811 | lower_bound |
| 0.30 | 1279 | lower_bound |

The Week 3 frontier selector is 5.438289351324354. Only .05 is certified complete conditional on this reconstructed model; wider counts are lower bounds because 14 QB partitions hit their safety maximum. Eleven exhausted their tolerance. Full expanded recall against the known union is 100% by construction, not a claim to cover the entire legal space.

Week 4's separate future reference counts are 38/111/205/258/397 at .05/.10/.15/.20/.30; only .05 is exact. Every other historical slate has no qualified reconstructed frontier denominator.

## 7. Old-vs-expanded recall

**Week 3 provisional; saved and replayed old recall is identical.**

| Tolerance | Old raw = admitted | Expanded205 | Expanded300 | Expanded400 | Expanded500 |
| --- | --- | --- | --- | --- | --- |
| 0.05 | 11/17 (64.7%) | 100.0% | 100.0% | 100.0% | 100.0% |
| 0.10 | 76/206 (36.9%) | 99.5% | 100.0% | 100.0% | 100.0% |
| 0.15 | 120/494 (24.3%) | 41.5% | 60.7% | 81.0% | 100.0% |
| 0.20 | 120/811 (14.8%) | 25.3% | 37.0% | 49.3% | 61.7% |
| 0.30 | 120/1279 (9.4%) | 16.0% | 23.5% | 31.3% | 39.1% |

These are recall against the known reconstructed frontier, not certified cross-slate means. Structural recall measures represented groups separately from roster recall; full grouped records at all tolerances are preserved. Week 4 old .20 recall was 84/258 (32.6%), with expanded targets 74.8%/97.7%/100%/100%. The similar generation deficit in Week 3 weakens the anomaly explanation, subject to its provisional status.

## 8. Generation-vs-admission decomposition

At .20, each Week 3 old control contains 120 of 811 known competitive rosters: **691 generation misses and zero admission misses**. Of these, 688 rosters are absent from both old controls, making the large discovery deficit robust to the three replay alternatives. The old raw and admitted pools are identical; there is no evidence of hidden old admission loss here.

Once discovery expands, admission becomes the measured bottleneck: targets 205/300/400/500 retain 205/300/400/500 of the 811 known competitive rosters, leaving 606/511/411/311 target-admission misses from this universe. Frontier coverage therefore depends on the objective: broad roster recall and preservation of the selected portfolio require different admitted sizes.

Week 4 had 174 generation misses and zero competitive admission misses at .20. Outside its competitive window, original raw admission reasons include 16 injury-risk rejects and 65 target-competition rejects. Those modern risk categories are not retrofitted into the legacy Week 3 eligibility frame.

## 9. Player coverage failures

Within .20, 142 players appear in known competitive rosters; the old pool covers 57, leaving **85 zero-coverage warnings**. Expanded admission warnings are 73/63/51/37 at targets 205/300/400/500; the full universe covers all 142. Warnings identify a known competitive opportunity, not mandatory exposure. Full raw coverage is 193 players out of 535 eligible.

`player_coverage.csv` audits every eligible canonical ID with salary, position, frozen mean/P90, ownership status, role evidence, best attainable selector, frontier gap/rank, raw/admitted counts and explicit omission reasons. The JSON retains target-specific audits. Competitive omitted examples include Jaxon Smith-Njigba, Tee Higgins and Chuba Hubbard. Ownership is diagnostic and remains unavailable at slate level; no actual result determined these examples. All configured pregame_role_label values are missing, so the single unclassified role group is not useful role-recall evidence; reconstructed offensive role classes/strength remain separate diagnostics.

## 10. QB coverage

All 25 eligible QB directions were queried. The full .20 frontier has 10 QB directions; old covers seven. Targets 205/300/400/500 represent 7/7/8/9 directions; full raw covers all 25 at any quality. A weak direction represented outside the competitive window is not competitive coverage. `qb_coverage.csv` retains every direction, best selector/gap, feasibility and coverage counts.

## 11. Game coverage

Competitive .20 canonical-game coverage increases from old 5/8 to full 8/8. Targets cover 6/6/6/7 games. Full raw includes 13 games at any quality. The fixed user's selected five still span five games; the twenty-entry thesis portfolio still spans four. More discovered game theses did not automatically diversify the selected portfolios.

## 12. Stack-family coverage

Competitive .20 family coverage increases from 16/39 to 39/39. Targets cover 16/18/23/28 families. Full raw has 150 families across all qualities. QB direction, partner count and bring-back presence define families consistently; individual partners are retained in diagnostics. Salary-tier coverage is 3/3 and positional coverage 5/5, which do not imply player-level completeness.

## 13. Thesis changes

Week 3 qualified competitive families expand **16→39**, with more competitive QB directions and games. This is new football breadth as well as deeper variants. Pareto families change 5→4 because newly discovered alternatives dominate prior families; the Pareto count is not a breadth metric. Frozen family records contain best-k mean/P90, ranks, selector drop, depth, representatives and dominance.

The dynamic five retains the same three games and 1/2/2 game allocation, changing Goff QB+3 from bring-back one to zero. Twenty retains seven selected families and four games, moving one entry from Shough QB+2 to Goff QB+3. Selected conclusions change modestly.

Week 4 differed: qualified families 4→7 and Pareto families 2→3, but competitive QB/game breadth remained 3/2. Its five concentrated all entries in JAX–CIN instead of four. Expanded discovery sometimes reveals new competitive directions, sometimes primarily deepens existing ones; it does not guarantee broader selected exposure.

## 14. Five-entry comparisons

| Universe | Entries | Selector sum | Mean sum | Player P90 sum | Solve s |
| --- | --- | --- | --- | --- | --- |
| old | 5 | 26.931683649 | 676.560 | 1183.130 | 1.014 |
| old_replayed | 5 | 26.931683649 | 676.560 | 1183.130 | 1.013 |
| full_expanded | 5 | 26.935940739 | 674.581 | 1186.144 | 9.813 |
| target_205 | 5 | 26.935940739 | 674.581 | 1186.144 | 1.513 |
| target_300 | 5 | 26.935940739 | 674.581 | 1186.144 | 1.903 |
| target_400 | 5 | 26.935940739 | 674.581 | 1186.144 | 2.570 |
| target_500 | 5 | 26.935940739 | 674.581 | 1186.144 | 2.859 |

Every Week 3 solve uses **overlap=4 and distinct QB paths=true**. All are feasible and optimal. Full and all admitted targets select the exact same five canonical rosters; old and replayed old select the same alternative five. The full objective lift is .004257, below .01. Mean falls 1.978 and summed player P90 rises 3.014. Both sets have five QBs/games/families, 27 players, average overlap 3.4 and maximum player exposure 100%, allowed by the frozen historical cap. No exposure setting was changed.

The unchanged dynamic thesis five uses overlap 6 and selects tolerance .05 in both old/full: selector 27.054652→27.058909, mean 687.438→685.460, P90 1196.009→1199.022. Game allocation remains ARI@SF 1, LV@NO 2, NYJ@DET 2. All four targets exactly match full. This shadow is distinct from the user's five-entry constraints.

Week 4 old and full fixed-user five had identical objective 27.202641 and canonical rosters. Expanded205 was infeasible under distinct-QB; 300 lost .210895 selector; 400/500 recovered the full optimum through tied alternatives. No complete enumeration of all feasible five-entry combinations was performed; best feasible quality and coverage were measured.

## 15. Twenty-entry comparisons

Week 3 dynamic thesis twenty, with the existing tolerance ladder and overlap policy unchanged, is optimal at tolerance .10 and overlap 6 for both old/full, with no unrestricted fallback.

| Metric | Old | Full expanded; all four targets |
| --- | --- | --- |
| Selector sum | 107.599110 | 107.650767 |
| Mean sum | 2741.001 | 2732.616 |
| Summed player P90 | 4777.950 | 4774.611 |
| NYJ@DET / LV@NO / CAR@CLE / ARI@SF | 7 / 8 / 3 / 2 | 8 / 7 / 3 / 2 |
| Maximum game exposure | 40% | 40% |
| Within-thesis average / maximum overlap | 5.294 / 6 | 5.367 / 6 |
| Across-thesis average / maximum overlap | 3.891 / 6 | 3.875 / 6 |

The .051656 selector lift is modest; mean and P90 both decline. Seven selected families and four games remain. All targets exactly reproduce full twenty rosters and allocations. Full solve takes .282 seconds. Frozen player exposure counts and representatives are retained.

Week 4 selector improved .0955, while mean/P90 declined; expansion removed the old unrestricted-tolerance fallback. Its 300 target matched full structural allocation/quality and 400/500 matched exact rosters. Summed player P90 is not a joint portfolio quantile.

## 16. Actual post-slate evaluation

**Descriptive only; attached after all pregame decisions were frozen.** There are 371 consistent canonical-player actuals. Missing/conflicting actuals remain unscoreable, never zero.

| Universe | Scoreable rosters | Best known actual | Regret against frozen known union |
| --- | --- | --- | --- |
| old | 109/120 | 157.0 | 35.84 |
| full_expanded | 1461/1589 | 192.84 | 0.00 |
| target_205 | 192/205 | 157.0 | 35.84 |
| target_300 | 284/300 | 157.0 | 35.84 |
| target_400 | 378/400 | 176.9 | 15.94 |
| target_500 | 466/500 | 176.9 | 15.94 |

The expanded maximum is 192.84 versus old 157.00, but the fixed user's best remains **137.10**. Its mean slips 114.828→114.688 (all five scored); the thesis five best remains 146.90 and mean slips 122.264→122.124. Twenty has only **18/20 scoreable entries** in each arm: known-subset best 147.40→148.40, mean 123.379→123.110, median 123.43→119.71, variance 265.249→196.779. These are not complete twenty-entry realized averages. All admitted targets select the same rosters, so their selected realized results are identical to full.

Selection regret references each arm's best known roster: user-five old 19.90 versus full 55.74; twenty old 9.60 versus full 44.44. The enlarged opportunity set increases this regret without proving the selector worsened. Discovery regret references the frozen union, not an actual-optimal legal lineup. No actual result selected a target or changed a pregame parameter.

Three fully scored Sunday Main label-matched fields total 41,616 entries: contests 195921989 (15,854), 195921990 (7,927), 195921991 (17,835). Top-1% score thresholds are 188.94/190.04/184.62; top-20% thresholds 149.94/152.18/147.80. The expanded raw maximum reaches top 1% in each field. Fixed-user five's best conservative top-percent ranks are 35.35%/38.39%/32.85%; thesis-five best 23.17%/25.63%/21.01%; expanded twenty's best 21.51%/24.11%/19.36%. One known twenty entry clears the third field's top-20% threshold, none the other two. No payout/cash-line evidence exists. These imported fields differ from the original draft's contest ID and exact slate membership is not independently certified; no own-contest ROI or cash-rate claim is made.

## 17. 205/300/400/500 comparison

**Required aggregate status: exact-certified N=0, so certified mean/median/worst distributions remain unavailable.** The following is the completed **provisional N=1** comparison; mean, median and worst equal this single case and are not estimates of a multi-slate distribution.

| Target | .20 recall | Zero-coverage warnings | QB | Games | Families | Five exact full | Twenty exact full | Admission s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 205 | 25.3% | ['0879dd26-248f-4f85-875a-f00e770a652b', '148d83d8-9e8c-4d3f-bb18-e2c78c9924cf', '154007f9-702e-497a-bdbd-bbf755e5cf3b', '17c94f64-c6b7-409d-bf2d-482c94910a5e', '1838dd60-35e8-4018-b307-39cde90e1f03', '1bc5ea87-e6bb-4608-a110-2b657344f1ed', '1cb58102-1426-459a-82cf-240882d90206', '1ccda8bb-bbcf-448d-ac27-311c81184fc5', '21e1ea77-10be-484d-85fd-90dd844747d5', '2314f0ae-dfd6-4494-87a9-a9e566ae9b5e', '252e3485-cb15-473b-a501-76694fa8abd0', '27c40adb-32b3-4412-8a87-d90f58882b72', '2aca41af-945f-4a4d-a94d-9520dd2e11cb', '2af6b6cb-8b3d-4895-9936-f22a63104487', '2f0659bc-74d2-48d0-a180-6bc1a979807e', '2f0bc3bc-4712-4976-b5a9-f4d89c3f7929', '2f11e002-760b-4e9a-a5b8-40b3227ec910', '32e4c447-467d-42e2-b855-adfad50ab73b', '376836fe-2a4f-42c0-99c4-dd1c9768034f', '37b2e76d-353b-4b03-8a4a-652774647103', '3a63877d-881f-4d87-8218-04c4f7fe8518', '4760ce22-5bab-4bb9-9b16-e9fb8fdaa727', '4825d517-2ed6-4cfe-848c-a004bab5af2a', '4a4df431-0fd9-4414-b3a4-d4a1d621a1e9', '4c409cae-1485-43ec-a0d9-a2bedeac3dde', '511918bb-8664-4c81-b565-189717cf36d3', '511c8587-8f93-42fc-afa7-1477defc41bd', '5f043c56-37db-4b0e-88d9-627a7c0ad47c', '6001e986-a704-4092-bd92-f5b7fba46765', '66c73392-886f-4fe8-96ab-ee24c990219b', '693463af-73ba-41d5-889c-388c36703430', '69b50fe9-c310-4417-9157-ac2eedca0d5f', '6bff4705-d1f3-41d3-9973-788b9b662234', '6d43b295-b04a-45fe-9c4a-7a9aa0996ea8', '7509113e-39e9-4e95-b8ad-99d78bc987d6', '7818d0f5-3b37-4274-9fc2-329afb6961ff', '7e7251d6-6edc-4448-83cd-da977eb9fcc9', '803866db-24cf-4a6d-9e40-6feb3813456d', '849e31ce-7572-42af-9c27-680862948ca8', '8503e22d-016f-43d3-b795-57c422d867d9', '877df359-7323-4f10-b694-b210bb4bd85f', '8fd869a9-df23-457a-91b5-4d2df2f81c0d', 'a48b2105-0cd9-4f35-844b-34f559ae2477', 'aa62b2ef-e5f6-4e61-9c0b-3bc9dda307d1', 'ab96444d-bab3-41d2-b4a9-b5d16fed57ff', 'add85ea5-9bb5-41f8-b136-7de0a4b7577d', 'af2cef33-41db-4417-b880-13885bff6921', 'b05ae628-27e9-4e5a-b7d7-449aeba78e5d', 'b5c3da49-f977-49ea-bdef-e18b45802d84', 'be56238b-7e9e-4d37-af84-1696c5b7f44a', 'be5d2df5-b0f6-432c-a033-d0e8b96437a2', 'bffad263-f398-4c55-85ce-77b4716dd0dc', 'c23e5343-efb7-4ef5-b334-fbdf2212dff5', 'c3d96a00-5572-4861-ac7a-2f6670a41525', 'c45b91f3-4b8a-4504-895f-01007268a251', 'c78ca065-994c-461a-85a9-95231a85c95c', 'c9728245-daaf-4f62-b2af-93be66ea23de', 'cc163351-baaa-4480-94c4-55654ed41c4a', 'ce37da63-fa80-4755-a1f5-ced80e4d9a3f', 'cf679d88-19e5-4cb9-8331-e68c99b9e919', 'da6a6dd3-66ca-4e31-a48c-daed7f0cb147', 'db10dcee-908b-4368-bb00-8204715a216d', 'e0afe83e-df6f-49bf-a3a5-4be8276e569d', 'e206707b-e50e-4864-996e-1bece35dd027', 'e4486866-1250-4f62-80ba-959f3de7571b', 'e5e86d75-9be3-448c-a9aa-ff11a284967c', 'e62b2592-4c10-4b02-94b8-c8c1aa157ce2', 'e6f33396-aab8-4d70-bc70-2717b52aa86c', 'e76d3393-159f-46d2-b18e-8fa80514bc78', 'f57e0806-3a25-44b1-9bcc-295699cb9536', 'f816bdba-894a-40e6-adf6-a3c2c0d659cb', 'f9244a63-468c-4229-bea5-7631467c6790', 'fd9dafeb-1072-47b0-a121-bd725df6fe31'] | 7 | 6 | 16 | YES | YES | 0.050 |
| 300 | 37.0% | ['0879dd26-248f-4f85-875a-f00e770a652b', '148d83d8-9e8c-4d3f-bb18-e2c78c9924cf', '154007f9-702e-497a-bdbd-bbf755e5cf3b', '17c94f64-c6b7-409d-bf2d-482c94910a5e', '1838dd60-35e8-4018-b307-39cde90e1f03', '1bc5ea87-e6bb-4608-a110-2b657344f1ed', '1ccda8bb-bbcf-448d-ac27-311c81184fc5', '21e1ea77-10be-484d-85fd-90dd844747d5', '2314f0ae-dfd6-4494-87a9-a9e566ae9b5e', '27c40adb-32b3-4412-8a87-d90f58882b72', '2af6b6cb-8b3d-4895-9936-f22a63104487', '2f0659bc-74d2-48d0-a180-6bc1a979807e', '2f0bc3bc-4712-4976-b5a9-f4d89c3f7929', '376836fe-2a4f-42c0-99c4-dd1c9768034f', '37b2e76d-353b-4b03-8a4a-652774647103', '3a63877d-881f-4d87-8218-04c4f7fe8518', '4760ce22-5bab-4bb9-9b16-e9fb8fdaa727', '4825d517-2ed6-4cfe-848c-a004bab5af2a', '4a4df431-0fd9-4414-b3a4-d4a1d621a1e9', '4c409cae-1485-43ec-a0d9-a2bedeac3dde', '511918bb-8664-4c81-b565-189717cf36d3', '511c8587-8f93-42fc-afa7-1477defc41bd', '5f043c56-37db-4b0e-88d9-627a7c0ad47c', '6001e986-a704-4092-bd92-f5b7fba46765', '66c73392-886f-4fe8-96ab-ee24c990219b', '693463af-73ba-41d5-889c-388c36703430', '6bff4705-d1f3-41d3-9973-788b9b662234', '6d43b295-b04a-45fe-9c4a-7a9aa0996ea8', '7818d0f5-3b37-4274-9fc2-329afb6961ff', '7e7251d6-6edc-4448-83cd-da977eb9fcc9', '803866db-24cf-4a6d-9e40-6feb3813456d', '849e31ce-7572-42af-9c27-680862948ca8', '8503e22d-016f-43d3-b795-57c422d867d9', '877df359-7323-4f10-b694-b210bb4bd85f', '8fd869a9-df23-457a-91b5-4d2df2f81c0d', 'a48b2105-0cd9-4f35-844b-34f559ae2477', 'aa62b2ef-e5f6-4e61-9c0b-3bc9dda307d1', 'ab96444d-bab3-41d2-b4a9-b5d16fed57ff', 'add85ea5-9bb5-41f8-b136-7de0a4b7577d', 'af2cef33-41db-4417-b880-13885bff6921', 'b05ae628-27e9-4e5a-b7d7-449aeba78e5d', 'b5c3da49-f977-49ea-bdef-e18b45802d84', 'be56238b-7e9e-4d37-af84-1696c5b7f44a', 'be5d2df5-b0f6-432c-a033-d0e8b96437a2', 'bffad263-f398-4c55-85ce-77b4716dd0dc', 'c23e5343-efb7-4ef5-b334-fbdf2212dff5', 'c45b91f3-4b8a-4504-895f-01007268a251', 'c78ca065-994c-461a-85a9-95231a85c95c', 'cc163351-baaa-4480-94c4-55654ed41c4a', 'ce37da63-fa80-4755-a1f5-ced80e4d9a3f', 'cf679d88-19e5-4cb9-8331-e68c99b9e919', 'da6a6dd3-66ca-4e31-a48c-daed7f0cb147', 'db10dcee-908b-4368-bb00-8204715a216d', 'e0afe83e-df6f-49bf-a3a5-4be8276e569d', 'e206707b-e50e-4864-996e-1bece35dd027', 'e5e86d75-9be3-448c-a9aa-ff11a284967c', 'e62b2592-4c10-4b02-94b8-c8c1aa157ce2', 'e6f33396-aab8-4d70-bc70-2717b52aa86c', 'e76d3393-159f-46d2-b18e-8fa80514bc78', 'f57e0806-3a25-44b1-9bcc-295699cb9536', 'f816bdba-894a-40e6-adf6-a3c2c0d659cb', 'f9244a63-468c-4229-bea5-7631467c6790', 'fd9dafeb-1072-47b0-a121-bd725df6fe31'] | 7 | 6 | 18 | YES | YES | 0.049 |
| 400 | 49.3% | ['0879dd26-248f-4f85-875a-f00e770a652b', '148d83d8-9e8c-4d3f-bb18-e2c78c9924cf', '154007f9-702e-497a-bdbd-bbf755e5cf3b', '17c94f64-c6b7-409d-bf2d-482c94910a5e', '1838dd60-35e8-4018-b307-39cde90e1f03', '1bc5ea87-e6bb-4608-a110-2b657344f1ed', '1ccda8bb-bbcf-448d-ac27-311c81184fc5', '2314f0ae-dfd6-4494-87a9-a9e566ae9b5e', '27c40adb-32b3-4412-8a87-d90f58882b72', '2af6b6cb-8b3d-4895-9936-f22a63104487', '2f0659bc-74d2-48d0-a180-6bc1a979807e', '2f0bc3bc-4712-4976-b5a9-f4d89c3f7929', '376836fe-2a4f-42c0-99c4-dd1c9768034f', '37b2e76d-353b-4b03-8a4a-652774647103', '3a63877d-881f-4d87-8218-04c4f7fe8518', '4760ce22-5bab-4bb9-9b16-e9fb8fdaa727', '4825d517-2ed6-4cfe-848c-a004bab5af2a', '4a4df431-0fd9-4414-b3a4-d4a1d621a1e9', '4c409cae-1485-43ec-a0d9-a2bedeac3dde', '511918bb-8664-4c81-b565-189717cf36d3', '511c8587-8f93-42fc-afa7-1477defc41bd', '5f043c56-37db-4b0e-88d9-627a7c0ad47c', '66c73392-886f-4fe8-96ab-ee24c990219b', '6bff4705-d1f3-41d3-9973-788b9b662234', '6d43b295-b04a-45fe-9c4a-7a9aa0996ea8', '7818d0f5-3b37-4274-9fc2-329afb6961ff', '803866db-24cf-4a6d-9e40-6feb3813456d', '849e31ce-7572-42af-9c27-680862948ca8', '877df359-7323-4f10-b694-b210bb4bd85f', '8fd869a9-df23-457a-91b5-4d2df2f81c0d', 'aa62b2ef-e5f6-4e61-9c0b-3bc9dda307d1', 'ab96444d-bab3-41d2-b4a9-b5d16fed57ff', 'add85ea5-9bb5-41f8-b136-7de0a4b7577d', 'af2cef33-41db-4417-b880-13885bff6921', 'b05ae628-27e9-4e5a-b7d7-449aeba78e5d', 'b5c3da49-f977-49ea-bdef-e18b45802d84', 'be56238b-7e9e-4d37-af84-1696c5b7f44a', 'be5d2df5-b0f6-432c-a033-d0e8b96437a2', 'bffad263-f398-4c55-85ce-77b4716dd0dc', 'c23e5343-efb7-4ef5-b334-fbdf2212dff5', 'c45b91f3-4b8a-4504-895f-01007268a251', 'cc163351-baaa-4480-94c4-55654ed41c4a', 'ce37da63-fa80-4755-a1f5-ced80e4d9a3f', 'cf679d88-19e5-4cb9-8331-e68c99b9e919', 'da6a6dd3-66ca-4e31-a48c-daed7f0cb147', 'e206707b-e50e-4864-996e-1bece35dd027', 'e6f33396-aab8-4d70-bc70-2717b52aa86c', 'e76d3393-159f-46d2-b18e-8fa80514bc78', 'f816bdba-894a-40e6-adf6-a3c2c0d659cb', 'f9244a63-468c-4229-bea5-7631467c6790', 'fd9dafeb-1072-47b0-a121-bd725df6fe31'] | 8 | 6 | 23 | YES | YES | 0.050 |
| 500 | 61.7% | ['0879dd26-248f-4f85-875a-f00e770a652b', '148d83d8-9e8c-4d3f-bb18-e2c78c9924cf', '154007f9-702e-497a-bdbd-bbf755e5cf3b', '17c94f64-c6b7-409d-bf2d-482c94910a5e', '1838dd60-35e8-4018-b307-39cde90e1f03', '1bc5ea87-e6bb-4608-a110-2b657344f1ed', '2314f0ae-dfd6-4494-87a9-a9e566ae9b5e', '2af6b6cb-8b3d-4895-9936-f22a63104487', '2f0659bc-74d2-48d0-a180-6bc1a979807e', '2f0bc3bc-4712-4976-b5a9-f4d89c3f7929', '37b2e76d-353b-4b03-8a4a-652774647103', '3a63877d-881f-4d87-8218-04c4f7fe8518', '4760ce22-5bab-4bb9-9b16-e9fb8fdaa727', '4825d517-2ed6-4cfe-848c-a004bab5af2a', '4c409cae-1485-43ec-a0d9-a2bedeac3dde', '511918bb-8664-4c81-b565-189717cf36d3', '5f043c56-37db-4b0e-88d9-627a7c0ad47c', '66c73392-886f-4fe8-96ab-ee24c990219b', '6bff4705-d1f3-41d3-9973-788b9b662234', '6d43b295-b04a-45fe-9c4a-7a9aa0996ea8', '7818d0f5-3b37-4274-9fc2-329afb6961ff', '803866db-24cf-4a6d-9e40-6feb3813456d', '849e31ce-7572-42af-9c27-680862948ca8', '877df359-7323-4f10-b694-b210bb4bd85f', '8fd869a9-df23-457a-91b5-4d2df2f81c0d', 'ab96444d-bab3-41d2-b4a9-b5d16fed57ff', 'add85ea5-9bb5-41f8-b136-7de0a4b7577d', 'b05ae628-27e9-4e5a-b7d7-449aeba78e5d', 'b5c3da49-f977-49ea-bdef-e18b45802d84', 'be5d2df5-b0f6-432c-a033-d0e8b96437a2', 'bffad263-f398-4c55-85ce-77b4716dd0dc', 'cc163351-baaa-4480-94c4-55654ed41c4a', 'ce37da63-fa80-4755-a1f5-ced80e4d9a3f', 'cf679d88-19e5-4cb9-8331-e68c99b9e919', 'e76d3393-159f-46d2-b18e-8fa80514bc78', 'f816bdba-894a-40e6-adf6-a3c2c0d659cb', 'f9244a63-468c-4229-bea5-7631467c6790'] | 9 | 7 | 28 | YES | YES | 0.049 |

For old, provisional .20 mean/median/worst is 14.8%, warnings 85, seven QBs/five games/16 families; exact matches to full are false. For expanded targets, feasibility and exact/structural/quality-equivalent match rates for both portfolios are 1/1. Memory is shared across targets, not four measured target-specific distributions. Total cost includes the common 405.09-second discovery phase plus admission/portfolio solves.

Week 3 all four targets preserve selected portfolio quality, despite 400 retaining only 49.3% of known .20 rosters. Week 4 needs 400 to preserve its fixed-user optimum and retains 100% at .20 with 400. Thus 400 is neither a universal recall guarantee nor a demonstrated minimum portfolio-preserving default. Dynamic admission remains an unvalidated hypothesis.

## 18. Exact/structural/quality-equivalent portfolio match rates

Exact means an identical unordered set of canonical rosters. Structural means identical QB/game/family allocation. Quality-equivalent means equal count and selector difference within .01/.05/.10 under identical constraints. Infeasible comparisons are unavailable, not zero-quality-loss successes.

Week 3 provisional 1/1: every target exactly and structurally matches full user-five, thesis-five and thesis-twenty, and passes every quality threshold. Old and replayed old match neither exact nor structural. Their user-five/thesis-five differences pass all three quality thresholds; twenty passes .10 but fails .01/.05. Full detailed match records are frozen.

Certified historical match rates have denominator zero and are unavailable. Week 4 is excluded from these rates: 205 fixed-user five is infeasible, 300 fails quality equivalence, 400/500 are structurally/quality equivalent through tied five rosters; twenty 300 is structural and 400/500 exact. See the separately hashed `week4_reference_metrics.json`.

## 19. Discovery-source contribution

Week 3 conservative first-source attribution starts from the union of saved and replayed old controls (123), so none of the three alternative old rosters receives discovery credit.

| Source | Solves | New rosters | New ≤.20 | Players | QB | Families | Selected5 | Selected20 | Worker s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| global_frontier | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1.6 |
| player_forced | 128 | 55 | 51 | 11 | 0 | 0 | 0 | 0 | 162.1 |
| qb_direction | 100 | 48 | 9 | 16 | 0 | 45 | 0 | 0 | 29.0 |
| qb_frontier | 1102 | 1019 | 604 | 76 | 18 | 44 | 1 | 5 | 1225.8 |
| qb_plus_3 | 50 | 45 | 2 | 22 | 0 | 45 | 0 | 0 | 12.4 |
| stack_partner | 434 | 299 | 22 | 10 | 0 | 0 | 0 | 0 | 89.8 |

Seven structural probes add no new rosters and cost 15.05 summed worker-seconds. Incremental .20 counts partition 688 common old-control misses: QB frontier 604, forced-player 51, partners 22, ordinary QB-direction nine, QB+3 two. Player/QB/family introduction counts cover all first-credited qualities, not only .20. Selected5 means the fixed user's five.

Attribution depends on declared event order; independent requests can rediscover the same roster. It is not a source-removal ablation. QB enumeration dominates useful coverage and contributes one selected five roster and five selected twenty rosters. Forced-player discovery finds 51 extra competitive rosters/11 players but no first-credited selected roster here. Partners have lower marginal competitive yield, yet add 22 competitive alternatives/10 players.

Week 4 likewise credited QB frontier 109 and forced-player 53 of 174 competitive additions, partners nine, ordinary directions one and QB+3 two. Structures duplicate existing candidates in both cases but are cheap. No source was removed: mandatory coverage and potential redundancy under other source orders require holdout ablations before pruning.

## 20. Runtime/memory

Week 3 archived old generation/description takes **1,611.98 seconds**. Expanded fresh discovery takes **405.09 seconds**, total expanded comparison **433.58 seconds**, with four workers and zero request-cache hits. Summed worker time exceeds elapsed wall time. Old bundled sequential CBC and expanded native CBC have different environments/parallelization, so the time difference cannot be attributed solely to architecture.

Admission costs are .050/.049/.050/.049 seconds. Fixed-user five costs are 1.513/1.903/2.570/2.859 seconds for targets 205/300/400/500, full 9.813, old 1.014. Full thesis five/twenty take .033/.282 seconds. Every discovery event has optimal or infeasible status: 1,818 optimal, four infeasible, zero unproven. Fourteen QB partitions are bounded by the safety maximum, not timeout. Every user portfolio returned optimal. Detailed per-arm thesis timings are frozen.

Parent peak RSS is 519.5 MiB; maximum child high-water RSS is 1,322.0 MiB, not simultaneous process-tree peak. Pregame serialized evidence is approximately 68 MB. Historical runtime distributions cannot be certified from one provisional observation. Week 4 prior fresh expanded discovery was 265.3 seconds; its repeated reference processing is not fresh runtime.

The overall task also incurred an avoidable failed freeze after the first completed expanded run, followed by a fresh rerun. An integer diagnostic-key serialization bug was fixed in the offline freeze helper and tested. These overheads are disclosed separately from the successful frozen experiment timing; no further optimizer runs or Week 4 HTML regeneration were performed.

## 21. Saturation analysis

The frozen independent request results were also re-ordered for a coverage-only diagnostic: all 720 mandatory non-frontier solver events first, followed by 1,102 QB-frontier events. This preserves the completed universe and does not execute an early-stop policy. After mandatory sweeps, quiet 50-event blocks at 850 and 900 would suggest stopping at 900, yet later blocks add **553 competitive rosters and 13 competitive player introductions**. A quiet pair is therefore unsafe even after mandatory sweep completion on this case.

The original ordering also exhibits premature quiet blocks. Week 4 previously appeared quiet around event 450, then events 850–963 added 56 competitive rosters. No stopping threshold was tuned, applied or promoted. Stable portfolio/thesis behavior at every prefix was not re-solved, so no portfolio-preserving stopping certificate exists. A dynamic target or early-stop rule requires prospective frozen development and independent chronological holdout evidence.

## 22. Chronological holdout

No independent chronological development/holdout split is possible: exact-certified historical N=0 and provisional historical N=1. Week 4 is future at the audit date and supplied the architecture, so it cannot be a historical holdout; Week 3 is retrospective development evidence. Repeated run refreshes, period aliases and contests on one slate are not independent observations. No source/target/stopping selection is claimed validated out of sample.

## 23. Promotion gate

**SHADOW LONGER.** Promotion fails on exact original-generation replay, independent chronological holdout, complete modern availability/source provenance and demonstrated target robustness. The evidence does support keeping generalized discovery in research: both available cases show large old-generation deficits and recurring useful QB/forced-player contributions. It does not establish material five-entry gains, a universal 400 target or profitable realized selection.

Production code hashes and all 75 original run objective/constraint configuration checksums must remain identical. The final verification artifact records that comparison, target 205 and no HTML regeneration. No production parameter or algorithm is changed by this report.

## 24. Recommended production architecture

Preserve the existing production generator and target **205**. This is operational continuity, not endorsement of its recall. Promote no discovery/admission change in this task.

The next research implementation should capture exact pre-lock code, solver environment, canonical input frame and all configuration alongside future controls, then shadow this same generalized discovery/admission architecture prospectively across independent chronological slates. Keep full raw universes and source lineage, four fixed admissions and existing portfolios. Confirm source-removal and dynamic-target hypotheses using pregame criteria and holdout, with actuals attached only after freeze. This is a future research requirement, not an additional optimizer run performed here.

## 25. Files changed

The primary deliverable is this report. Offline helpers are in `backend/app/product_services/classic_discovery_validation.py`; focused tests are in `backend/app/tests/product/test_classic_discovery_validation.py`. The catalog CLI is `scripts/audit_classic_discovery_cohort.py`. README and release notes describe the updated qualification and outcome.

Durable evidence is under `artifacts/classic_discovery_multi_slate/`: inventory/cohort/source reconstruction audits; the archived backend and hashed Week 3 reconstructed frames; original replay and exact-failure assessment; complete expanded request cache and pregame comparison; per-player/QB audits; pregame-derived summary/source/saturation records; postgame attachment/descriptive metrics; final tests and production verification. Research/replay/postgame/summary scripts are saved beside these records. These offline files are not imported into production routing. Existing unrelated workspace changes are preserved.

## 26. Tests

**228 relevant tests passed in 10.38 seconds; compilation checks passed.** Final verification confirms five protected production code hashes and all 75 original objective/constraint checksums are identical.

Final relevant checks cover validation chronology/freeze/integrity, candidate completeness, prospective safety, small-field generation, thesis shadows/completion, optimizer coverage/effectiveness/modes and cash-stack replay. The final test transcript is `artifacts/classic_discovery_multi_slate/continuation_final_tests.txt`; final code/config verification is `continuation_final_production_verification.json`.

Meaningful new checks include matching archived/current scores and mathematical models, keeping failed exact replay unqualified, same-universe admissions, fixed five constraints, pregame-before-postgame hash links, integer-key freeze/reload integrity, rejection of actuals nested under numeric diagnostic keys and duplicate serialized JSON keys. Frozen inputs are not mutated by the normalization fix. No production code modification or new dependency is required.

## 27. Remaining uncertainty

The exact solver environment and three old roster differences remain unresolved; the legacy 120-candidate control differs from modern 205 and has no aggregate exposure caps. Modern injury/source evidence is incomplete. Wider legal frontiers are bounded lower counts. There is one provisional historical case, no certified multi-slate distribution or holdout, no removal ablation and incomplete twenty-entry actual scoring. Field comparisons are reference fields, not own-contest payout evidence. The conclusions below retain these limits.

### Does expanded discovery generalize?

**BORDERLINE.** It adds substantial useful coverage in one provisional historical slate and the separate Week 4 diagnostic. Independent chronological generalization is unvalidated.

### Is incomplete generation a recurring problem?

**YES, provisionally in the available checks.** Week 3 and Week 4 both show large generation deficits; certified historical recurrence cannot be estimated from N=0.

### Is generation or admission the dominant source of competitive misses?

**Generation in the old pipelines.** Week 3 has 691 generation/zero admission misses at .20, with 688 absent from both old controls; Week 4 has 174/zero. After expansion, fixed target admission is a substantial coverage bottleneck.

### Which discovery sources add the most useful coverage?

QB frontier enumeration first, generic forced-player discovery second; partner sweeps add useful secondary breadth. These contributions recur in the two available cases.

### Which sources are low-value relative to compute?

Partners have smaller marginal competitive yield; global/structural probes add no unique rosters here but cost little. Attribution is order dependent. No removal is justified without ablations and holdout.

### What admitted candidate target should production use?

**205, preserving current production.** No expanded-discovery target is approved for promotion; dynamic remains unvalidated.

### Does 400 generalize as the best default?

**NO demonstrated generalization.** Week 3's 205 already preserves full selected portfolios, while 400 covers only 49.3% of its known .20 frontier. Week 4 requires 400 to preserve its fixed-user optimum. No universal best default is established.

### Does expanded discovery materially change thesis conclusions?

**YES for provisional Week 3 competitive breadth; modestly for selected theses.** Families expand 16→39 and QB/game breadth grows, but selected game allocations mostly persist. Week 4 mainly deepens existing directions. The effect is not uniform.

### Does it materially improve the user's five-entry feasible set?

**No demonstrated material best-quality improvement.** Week 3's optimal fixed-user selector rises only .004257 with unchanged QB/game breadth; Week 4's full optimum is unchanged. All feasible combinations were not enumerated.

### Does it materially improve the 20-entry thesis portfolio?

**A modest improvement, not established material generalization.** Week 3 selector rises .051656 with unchanged four-game breadth/40% maximum game exposure and lower mean/P90. Week 4 removes a fallback and improves .0955; no holdout confirms reliability.

### What do realized results show?

**Descriptive only.** Week 3 best known raw actual rises 157.00→192.84, but user's selected best stays 137.10 and five-entry means decline slightly. Twenty's 18 known entries improve best by one point while their partial mean declines. Missing actuals remain missing. No outcome informed pregame decisions or the target recommendation.

### Is expanded discovery ready for production?

**SHADOW LONGER.** Exact replay, trustworthy modern snapshots and independent chronological holdout remain unmet.

### What exact code/config change should be promoted next?

**None yet.** Keep production generator/205 target and every projection, selector, correlation, ownership, risk, exposure, overlap, distinct-QB and thesis setting unchanged. Next implement complete prospective control provenance in research and validate the frozen generalized shadow across chronological slates before proposing production promotion.
