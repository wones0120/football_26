# Sunday Main Tiers: full-roster football review, v5

Recorded October 16, 2026. Preliminary research; **review recommendation only**. Original v4 saved lineup and its download remain unchanged. No new optimizer run, selection, projection, model, user constraint, or contest entry was changed.

My provisional choice is **Josh Allen / Kenneth Walker III / Puka Nacua / Kyren Williams / Aaron Rodgers / Ashton Jeanty**. Its unchanged projected mean is **122.582**, versus **123.065** for the fresh exact highest-mean roster, which uses Adams instead of Jeanty. Confidence in preferring the former's full-lineup path is **modest**. We do not have calibrated joint Tiers outcomes demonstrating it is more likely to win. The 0.483 mean cost is explicit, not a hidden projection penalty or new teammate rule.

## What changed in the inputs

The original v4 Allen/Henry/Puka/Kyren/Cousins/Jeanty roster was 123.108 on October 15's 19:17:26 UTC projections. On the completed **October 16 14:58:29 UTC** frozen source it is **122.037**, a source/model-input change of **−1.071** before any selection change. Cousins alone falls from 21.760 to 20.278. Walker now narrowly leads Henry, Rodgers narrowly leads Cousins, and Adams leads Jeanty. Do not attribute those changed rankings to a new construction method.

Source: completed preparation `01361b85-f0fe-4b20-9253-334e6b95ebea`, projection `c8869a96-440c-4c36-aead-3614d6ef4d97`, frozen snapshot `6d662321caa3a513bb7720d68f836aca4cad96581314757c5e35d7d794ae207a`. Its original hash and contract were verified. This final frozen source arrived while the review was being written. All 40 offensive means are **exactly equal** to the earlier completed 14:50:08 UTC b13 source used for initial calculations; [cross-source proof](source_transition.json) preserves both identifiers. No partial output was consumed. Tiers contains no DST, so the separate defense change does not alter these comparisons.

The source is explicitly `PRELIMINARY_RESEARCH`, `entry_ready=false`, with exclude-unknown-and-questionable assumptions. Its internal readiness label is not final-entry clearance. All 40 Tiers canonical players are present in the source; Hurts has no eligible projection and is OUT. Native Q designations for Olave, Flowers and Boston remain excluded, even where the Classic source labels their roster status ACT. Blank final designations do not clear them.

Official club pages for all 18 represented teams were captured at approximately **14:54–14:55 UTC**, preserving raw bytes, hashes, HTTP clocks and parsed tables in [source manifest](primary_sources/manifest.json). These captures are evidence for this review, not a silent ingest or model refresh. Friday/final statuses are not yet established. Raiders Thursday: **Jeanty foot FP; Bowers knee improved LP→FP; Nailor concussion DNP→LP**. Bills Moore DNP, Palmer LP and Ed Oliver DNP remain relevant uncertainties; Spencer Brown improved to FP. Correction: an earlier progress note misread the Raiders table as Wednesday-only; the preserved table does include Thursday. [Raiders official report](https://www.raiders.com/team/injury-report/).

Markets in the frozen source were observed at **14:57:06 UTC**: BUF–LV 53.5, BUF −4.5 (29.0/24.5 implied); ARI–LAR 51.5, LAR −12.5 (32.0/19.5); LAC–KC 41.5, KC −7.5; PIT–TB 39.5, PIT −2.5; CAR–PHI 38.5, CAR −3.5. These are market expectations, not pace measurements, guaranteed scores, or branch probabilities. No verified current neutral pace/opponent-adjusted efficiency estimate was added; do not turn the total into an asserted possession count.

## How the preferred full roster succeeds

Allen creates points through passing and his own rushing, with enough Las Vegas production to keep Buffalo using its offense. Jeanty supplies a specific opposing response through catches and combined yardage; this does not require Cousins himself to finish as the best T5 quarterback. KC can build a lead with Walker's rushing workload. In Los Angeles, Puka accumulates catches/yardage while Kyren contributes on the ground and through his own receiving role; both can succeed in an efficient Rams offense without both requiring every touchdown. Rodgers needs Pittsburgh to finish a useful share of its drives through the air while Tampa Bay sustains enough offense to maintain opportunity. This is four games with complementary mechanisms, not six unrelated ceiling forecasts.

The largest remaining shared dependencies are **Puka+Kyren's Rams offense** and **Allen+Jeanty's BUF–LV environment**. If Arizona cannot respond, Rams pass volume may stop early; if Las Vegas stalls or Buffalo's receiver issues degrade drives, the Allen/Jeanty branch can both underperform. Walker still needs rushing efficiency/goal-line access; Rodgers depends strongly on passing touchdowns. This roster is not insulated from shared failure just because it has four games.

Tampa Bay's QB situation is a material caveat: the source lists Jalon Daniels as expected starter, while the current official report has Baker Mayfield thumb DNP Wednesday/Thursday. That is not a verified strong opponent response. A weak Tampa offense could leave Pittsburgh running/protecting a lead and undermine Rodgers. His current 0.354 mean edge over Cousins is too small to override adverse final role/availability news. [Steelers/Buccaneers official report](https://www.steelers.com/team/injury-report/).

## Why each tier, and what changes the choice

**T1 — Allen 26.098; Stafford 24.932, gap 1.166.** Allen's observed Weeks 3–5 rushing was 8/5/10 carries and 2/1/1 rushing TDs; Week 5's 121 rushing yards is an observed outlier, not an assumption. He has a non-receiving-dependent scoring route. Stafford's 55/51/54 attempts and 390/317/383 passing yards provide a serious alternative if Arizona sustains a pass-heavy game. Stafford with Puka/Kyren is a coherent Rams-concentrated branch, but adds that game's dependence and requires passing TDs plus enough Kyren production. Mahomes (20.385) and Maye (19.213) are other-game alternatives at costs of 5.713 and 6.885 relative to Allen; neither becomes superior merely by removing BUF exposure. Mahomes knee FP, Rice DNP and KC tackle Simmons LP complicate the passing alternative. [Chiefs official report](https://www.chiefs.com/team/injury-report/).

**T2 — Walker 19.220; Henry 19.029, gap 0.192.** Walker's latest three observed games, Weeks 2–4, have 24/18/22 carries. Only the first has major receiving volume (10 targets, then 2/1), so this is principally a rushing/goal-line case, not a promised receiving role. KC −7.5 provides a plausible lead-and-run branch; it is not evidence of an automatic Walker touchdown. Henry is almost tied and has the more recent observed 26/23/24 carries in Weeks 3–5, with 1/2/2 targets. He becomes my alternative if Baltimore repeatedly reaches scoring range and KC's lead or Walker's role does not materialize. The missing Walker Week 5 game row is not assigned an invented reason. Bijan 18.235 is also live if Atlanta's close CHI game produces sustained rushing plus his Week 5 receiving involvement; do not claim Henry or Walker is certain to lead this tier.

**T3 — Puka 22.152; Bowers 15.793, gap 6.359.** Puka's latest observed games (Weeks 1/4/5, not three consecutive weeks) show 9/12/24 targets. Twenty-four is not a forecast. His catch/yardage path gives the roster a way to score before requiring multiple Rams touchdowns. Bowers Thursday FP is encouraging but not final clearance. A Vegas-heavy passing response with Bowers concentrated underneath and reduced Rams pass volume favors Bowers, at a substantial mean cost; it also creates direct Vegas target competition with Jeanty. McMillan 14.517 is the other eligible choice; Olave remains native Q/excluded.

**T4 — Kyren 19.907; Cook 16.179, gap 3.728.** Kyren's Weeks 3–5 carries 15/16/16 and targets 7/13/8 show a receiving route alongside rushing work. Puka catches and Kyren carries are not the same physical opportunity. Passing TDs to Kyren can benefit the Rams QB but still take a receiving TD away from other Rams receivers; no score event is counted as two team touchdowns. A fast Rams lead may favor Kyren but reduce Puka's late opportunity. Cook wins the alternative if Buffalo scores primarily through its backfield; that competes with Allen's rushing TD route rather than removing all dependency. Warren 15.059, McBride 14.941, Hubbard 14.505, London 13.789 and Nabers 13.448 all need stronger role/game-specific branches to justify their substantial gaps. Flowers remains Q/excluded.

**T5 — Rodgers 20.632; Cousins 20.278, gap 0.354; Young 20.253, gap 0.379.** Rodgers had 34/40/31 attempts and three passing TDs in each of Weeks 3–5; three TDs each week is not a guaranteed sustainable rate. PIT's 21-point implied team total and Tampa QB uncertainty are serious contrary evidence. Cousins' 33/52/28 attempts, 248/365/243 yards and 3/2/1 TDs in the same weeks show a credible passing response but variable opportunity. Choose Cousins over Rodgers if Vegas stays competitive by throwing and Pittsburgh wins through rushing/defense. Young's latest observed Weeks 2–4 had 36/48/41 attempts and 287/291/329 yards, but the missing Week 5 row remains unexplained, and Carolina's current 21 implied points plus McKee replacing Hurts do not assure sustained pass volume. Young knee FP is practice evidence, not game clearance. Shough 18.650, Brissett 18.420, Winston 16.268 and Jones 14.310 remain lower-mean alternatives; Hurts is unavailable. [Eagles official McKee report](https://www.philadelphiaeagles.com/news/tanner-mckee-will-be-ready-for-his-moment-2026-nfl-week-6-carolina-panthers).

**T6 — Analyst Jeanty 14.573; mean leader Adams 15.056, cost 0.483.** Jeanty's Weeks 3–5 targets 3/8/6, receptions 3/6/3 and receiving yards 37/68/50 support a receiving response to Allen. His carries **19→15→10**, rushing yards 56/58/27 and snap share **84%→67%→53%** argue against casually assigning an expanded workload or multiple rushing TDs. The preference is conditional on maintaining that receiving role; it is not a numeric share boost. Adams had 13/9/7 targets and 7/4/5 catches; his last game's two receiving TDs can recur but should not be silently projected. Adams is absolutely viable if the Rams distribute enough passing TDs/yardage to Puka and Adams while Kyren gets ground/receiving work. This is the exact-mean alternative, not rejected for being a third Ram. I narrowly prefer the Jeanty response branch at this tiny mean cost; there is no measured probability edge.

Michael Wilson 14.358 costs only 0.214 versus Jeanty and can keep Arizona responding to the Rams; his targets fell 17→13→7 and last game was 4 catches/30 yards, so the bring-back is conditional, not automatic. Irving 13.779 costs 0.793 versus Jeanty and supplies an opposing response to Rodgers. He had 15/16/21 carries but only 4/0/3 targets; Week 5's 165 rushing yards/two combined TDs followed 46/61 rushing yards and zero TDs. The PIT–TB branch can succeed without a high total, but repeating that spike is not the baseline case. Swift, Garrett Wilson, Skattebo, Stevenson, Likely, Tyler Warren and Kelce trail further; Boston remains Q/excluded. No lower-total player is categorically banned.

## Keeping Allen+Cousins+Jeanty is defensible

It is not inherently an incompatible QB/QB/RB combination. A Cousins completion to Jeanty creates passing yards for Cousins and receiving yards/PPR for Jeanty from **one** physical play. A Cousins-to-Jeanty TD gives both fantasy scoring without requiring two Raiders TDs. Allen can benefit when those Raiders drives keep Buffalo responding. Other Cousins TDs can go to Bowers/receivers while Jeanty succeeds on catches/yardage; not everyone needs multiple touchdowns.

The shared downside is real: stalled Raiders drives hurt both Vegas players and can reduce Buffalo's urgency. Pure Jeanty rushing TDs take Raiders TD opportunities from Cousins; Bowers/other receivers compete for Jeanty's targets; Jeanty's recent declining snap/carry volume weakens an unquestioned bell-cow case. The updated market still expects 24.5 Vegas points, but it does not prove that all three beat their tiers. Keeping this trio with Walker has **122.228** mean, only 0.354 below the preferred Rodgers version. It is a reasonable explicitly chosen BUF–LV scoring branch, not a roster that requires repair solely because it contains three players from one game.

## Complete legal alternatives under the same fresh source

Every roster below has one native player per T1–T6, six distinct canonical players, no retained Q/OUT player, and at least two NFL games. Salary is **not applicable**. No settings were relaxed. These are conditional comparisons, not independent probability-weighted scenarios or newly saved optimizer outputs.

| Variant | T1 | T2 | T3 | T4 | T5 | T6 | Mean | Gap vs mean leader | Games |
|---|---|---|---|---|---|---|---:|---:|---:|
| original_roster_fresh_means | Josh Allen | Derrick Henry | Puka Nacua | Kyren Williams | Kirk Cousins | Ashton Jeanty | 122.037 | -1.028 | 3 |
| fresh_exact_highest_mean | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Davante Adams | 123.065 | +0.000 | 4 |
| analyst_balanced_path | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Ashton Jeanty | 122.582 | -0.483 | 4 |
| retain_vegas_trio | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Kirk Cousins | Ashton Jeanty | 122.228 | -0.837 | 3 |
| young_four_game_alternative | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Bryce Young | Ashton Jeanty | 122.204 | -0.862 | 4 |
| irving_opponent_response | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Bucky Irving | 121.789 | -1.276 | 4 |
| wilson_rams_bringback | Josh Allen | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Michael Wilson | 122.368 | -0.697 | 4 |
| stafford_rams_passing | Matthew Stafford | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Ashton Jeanty | 121.416 | -1.649 | 4 |
| mahomes_different_game | Patrick Mahomes | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Ashton Jeanty | 116.869 | -6.196 | 4 |
| maye_different_game | Drake Maye | Kenneth Walker III | Puka Nacua | Kyren Williams | Aaron Rodgers | Ashton Jeanty | 115.697 | -7.368 | 5 |
| henry_workload_alternative | Josh Allen | Derrick Henry | Puka Nacua | Kyren Williams | Aaron Rodgers | Ashton Jeanty | 122.391 | -0.674 | 4 |

Preferred roster native identity:

| Tier | Player | Native ID | Mean |
|---|---|---|---:|
| T1 | Josh Allen | 44498892 | 26.098 |
| T2 | Kenneth Walker III | 44498897 | 19.220 |
| T3 | Puka Nacua | 44498900 | 22.152 |
| T4 | Kyren Williams | 44498906 | 19.907 |
| T5 | Aaron Rodgers | 44498916 | 20.632 |
| T6 | Ashton Jeanty | 44498921 | 14.573 |


The exact-mean Adams roster can succeed through concentrated Rams offense: Puka catches/yardage, Adams receiving scores, Kyren rushing/receiving production, while Allen, Walker and Rodgers succeed independently of those individual Rams targets. It fails jointly if the Rams stall or score via other players; a large lead can help Kyren while truncating receivers' volume. It is a valid option, not an automatic improvement from removing a Raider.

The Irving variant has a constructive PIT–TB success path: Irving carries/receives enough to keep Tampa's offense moving while Rodgers answers through passing TDs. It also puts two players in a game with substantial quarterback uncertainty and gives up 1.276 mean versus the exact leader. The Wilson variant concentrates two sides of ARI–LAR, not more independent games; it needs Arizona's passing offense to sustain that game. Stafford deliberately concentrates Rams passing; Mahomes/Maye deliberately change T1 environment at large mean costs. None is justified simply by counting teammates.

## Scope, verification and remaining uncertainty

All 40 players and old/fresh means are retained in [all-player audit](all40_projection_comparison.json); canonical raw prior-week aliases/ingest provenance and snap observations are retained in [workload evidence](observed_workload.json). Raw weekly observations are history, not opponent-adjusted projections or current workload guarantees. Current pace, exact red-zone allocation, and an empirically calibrated joint-outcome model are missing. The earlier touch-only construction prototype remains rejected/inactive; no empirical same-team pair rate is imported as a Tiers probability.

[Comparison](comparison.json) records every full roster, native IDs, canonical IDs, means, game count, source hashes and explicit research-only state. [Verification](verification.json) checks the frozen snapshot's hash/contract, all40 coverage, native tiers, distinct identity, availability policy, game minimum and exact summed means. No claim of scenario win probability, lineup P90, optimal tournament portfolio, or final entry readiness is made.

The original app saved run **1bc9d189…** and its previously verified CSV still contain Allen/Henry/Puka/Kyren/Cousins/Jeanty. **This recommendation is published in the app's Analyst Reports library, not applied to the Tiers lineup selector.** Consequently no new CSV is advertised as this recommendation. Revisit final Friday/game-day statuses and confirmed QB roles before treating any variant as entry-ready. No submission occurred.


## All 40 native candidates

| Tier | Player | Native ID | Team | Old mean | Fresh mean | Eligibility evidence |
|---|---|---|---|---:|---:|---|
| T1 | Josh Allen | 44498892 | BUF | 26.309 | 26.098 | Sourced active role; final game clearance unverified |
| T1 | Drake Maye | 44498893 | NE | 18.887 | 19.213 | Sourced active role; final game clearance unverified |
| T1 | Patrick Mahomes | 44498894 | KC | 19.992 | 20.385 | Sourced active role; final game clearance unverified |
| T1 | Matthew Stafford | 44498895 | LAR | 25.216 | 24.932 | Sourced active role; final game clearance unverified |
| T2 | Bijan Robinson | 44498896 | ATL | 18.272 | 18.235 | Sourced active role; final game clearance unverified |
| T2 | Kenneth Walker III | 44498897 | KC | 18.497 | 19.220 | Sourced active role; final game clearance unverified |
| T2 | Derrick Henry | 44498898 | BAL | 18.809 | 19.029 | Sourced active role; final game clearance unverified |
| T2 | Jonathan Taylor | 44498899 | IND | 15.544 | 15.599 | Sourced active role; final game clearance unverified |
| T3 | Puka Nacua | 44498900 | LAR | 21.814 | 22.152 | Sourced active role; final game clearance unverified |
| T3 | Chris Olave | 44498901 | NO | 14.809 | 14.717 | Excluded: native Q |
| T3 | Tetairoa McMillan | 44498902 | CAR | 14.594 | 14.517 | Sourced active role; final game clearance unverified |
| T3 | Brock Bowers | 44498903 | LV | 15.700 | 15.793 | Sourced active role; final game clearance unverified |
| T4 | James Cook III | 44498904 | BUF | 16.183 | 16.179 | Sourced active role; final game clearance unverified |
| T4 | Jaylen Warren | 44498905 | PIT | 14.787 | 15.059 | Sourced active role; final game clearance unverified |
| T4 | Kyren Williams | 44498906 | LAR | 19.785 | 19.907 | Sourced active role; final game clearance unverified |
| T4 | Chuba Hubbard | 44498907 | CAR | 14.575 | 14.505 | Sourced active role; final game clearance unverified |
| T4 | Zay Flowers | 44498908 | BAL | 15.095 | 14.915 | Excluded: native Q |
| T4 | Drake London | 44498909 | ATL | 13.770 | 13.789 | Sourced active role; final game clearance unverified |
| T4 | Malik Nabers | 44498910 | NYG | 13.421 | 13.448 | Sourced active role; final game clearance unverified |
| T4 | Trey McBride | 44498911 | ARI | 14.983 | 14.941 | Sourced active role; final game clearance unverified |
| T5 | Jalen Hurts | 44498912 | PHI | — | — | Excluded: OUT/missing projection |
| T5 | Jacoby Brissett | 44498913 | ARI | 18.379 | 18.420 | Sourced active role; final game clearance unverified |
| T5 | Bryce Young | 44498914 | CAR | 20.573 | 20.253 | Sourced active role; final game clearance unverified |
| T5 | Tyler Shough | 44498915 | NO | 18.630 | 18.650 | Sourced active role; final game clearance unverified |
| T5 | Aaron Rodgers | 44498916 | PIT | 20.318 | 20.632 | Sourced active role; final game clearance unverified |
| T5 | Kirk Cousins | 44498917 | LV | 21.760 | 20.278 | Sourced active role; final game clearance unverified |
| T5 | Daniel Jones | 44498918 | IND | 14.368 | 14.310 | Sourced active role; final game clearance unverified |
| T5 | Jameis Winston | 44498919 | NYG | 16.269 | 16.268 | Sourced active role; final game clearance unverified |
| T6 | D'Andre Swift | 44498920 | CHI | 12.899 | 12.771 | Sourced active role; final game clearance unverified |
| T6 | Ashton Jeanty | 44498921 | LV | 14.631 | 14.573 | Sourced active role; final game clearance unverified |
| T6 | Bucky Irving | 44498922 | TB | 13.742 | 13.779 | Sourced active role; final game clearance unverified |
| T6 | Rhamondre Stevenson | 44498923 | NE | 11.250 | 11.206 | Sourced active role; final game clearance unverified |
| T6 | Cam Skattebo | 44498924 | NYG | 11.395 | 11.392 | Sourced active role; final game clearance unverified |
| T6 | Garrett Wilson | 44498925 | NYJ | 12.243 | 12.205 | Sourced active role; final game clearance unverified |
| T6 | Michael Wilson | 44498926 | ARI | 14.404 | 14.358 | Sourced active role; final game clearance unverified |
| T6 | Davante Adams | 44498927 | LAR | 14.593 | 15.056 | Sourced active role; final game clearance unverified |
| T6 | Denzel Boston | 44498928 | CLE | 9.348 | 9.316 | Excluded: native Q |
| T6 | Travis Kelce | 44498929 | KC | 9.477 | 9.482 | Sourced active role; final game clearance unverified |
| T6 | Tyler Warren | 44498930 | IND | 10.490 | 10.496 | Sourced active role; final game clearance unverified |
| T6 | Isaiah Likely | 44498931 | NYG | 11.148 | 11.079 | Sourced active role; final game clearance unverified |

