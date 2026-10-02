# Week 4 Thursday Showdown game-day finalization: PIT @ CLE

Decision frozen 2026-10-01 07:05 AM EDT; kickoff October 1, 2026, 8:15 PM EDT. **ENTRY READY: NO.** This is the completed morning refresh and provisional three-entry decision. Final game-day inactives/elevations and a near-lock source refresh are still outstanding. No entry or upload file was created.

The fresh joint solve independently retains **DK Metcalf / Deshaun Watson / Jerry Jeudy**. All three pairwise overlaps are four of six. Metcalf is the least costly shared core to reduce: total selector cost **0.005571**, projected mean cost **4.32**, summed P90 cost **5.17** across three entries. The full comparison is below.

## 1. Source refresh

The new hashed bundle is [20261001T103726Z game-day bundle](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z). The immutable overnight control is [WEEK4_THURSDAY_SHOWDOWN_PRELOCK_AUDIT.md](/Users/wones/git/football_26/WEEK4_THURSDAY_SHOWDOWN_PRELOCK_AUDIT.md). Sources were downloaded again; matching salaries were not silently carried forward.

Fresh official [DK salary download](https://www.draftkings.com/lineup/getavailableplayerscsv?draftGroupId=154084) observed **2026-10-01T10:42:57.027782+00:00**, SHA-256 `e7429b64d15e76b236e15d47422d95885cdf9c565129887f9872f889c15f5c73`. The [official contest](https://www.draftkings.com/draft/contest/196187074) identifies PIT @ CLE, draft group **154084**, and the correct 00:15 UTC lock. This was a direct public official download, **not an authenticated account-session download**. Chrome access was unavailable. The primary-source file nevertheless verifies every native slot against canonical ingestion.

**102/102 native DK slots, 51/51 canonical players, all CPT/FLEX pairs verified**: native ID, name, position, roster position, team, game, salary, status and 1.5× CPT salary. Salaries and IDs are unchanged; Dowdle and Wallace statuses changed Q→OUT in both slots. [Complete row-level verification](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/salary_verification.json).

Operations FanDuel injury run `06bd5a44-067b-4f8e-ad30-60174f321906` completed at **2026-10-01 10:40:26.706001 UTC**: 52 raw/curated rows; checksum `507ed1697815ec4db6f62ce80b185c966e8b1af2c219aa3fd8678e5a2d4fa6bc`. Its immutable capture is linked to that existing import; it was not reimported. All DK-relevant FD identities resolve. The single unresolved FD row is Noah Igbinoghene, labeled WR by FD while the official CLE depth chart lists CB. It remains queued and contributes no model injury fact; he is absent from DK’s 51-player pool. A blank FanDuel flag does not confirm a player will dress.

| Source | Fresh observation UTC | Evidence |
| --- | --- | --- |
| cle_depth | 2026-10-01T10:43:34.309713+00:00 | [primary page](https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers); SHA `efd8df25d625` |
| cle_injuries | 2026-10-01T10:43:34.309591+00:00 | [primary page](https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report); SHA `2e07f737462f` |
| cle_news | 2026-10-01T10:43:34.309457+00:00 | [primary page](https://www.clevelandbrowns.com/news/all); SHA `95c8f109af62` |
| cle_roster | 2026-10-01T10:43:34.309781+00:00 | [primary page](https://www.clevelandbrowns.com/team/players-roster/); SHA `e972c467b2ca` |
| cle_transactions | 2026-10-01T10:43:34.625149+00:00 | [primary page](https://www.clevelandbrowns.com/team/transactions/); SHA `4a3687ed2926` |
| market | 2026-10-01T10:43:34.637134+00:00 | [primary page](https://dknetwork.draftkings.com/moneyline-total-spread/); SHA `05cb536c2696` |
| pit_depth | 2026-10-01T10:43:34.309662+00:00 | [primary page](https://www.steelers.com/team/depth-chart/); SHA `753df799c267` |
| pit_inactives | 2026-10-01T10:43:34.309223+00:00 | [primary page](https://www.steelers.com/news/archive/inactives/); SHA `ea1251cd78ad` |
| pit_injuries | 2026-10-01T10:43:34.309522+00:00 | [primary page](https://www.steelers.com/news/week-4-injury-report-browns); SHA `380cd7e949bd` |
| pit_roster | 2026-10-01T10:43:34.309749+00:00 | [primary page](https://www.steelers.com/team/players-roster/); SHA `a8fbb562291a` |
| pit_transactions | 2026-10-01T10:43:34.588627+00:00 | [primary page](https://www.steelers.com/team/transactions/); SHA `5a7f8b3cf28b` |
| weather | 2026-10-01T10:43:34.637781+00:00 | [primary page](https://api.weather.gov/points/41.506,-81.699); SHA `aec924de3019` |

Raw bytes, parsed pages, ingest/source lineage and weather hourly JSON are retained. Projection cutoff **2026-10-01 06:46:13.911749-04:00**; projection run `e62f4bbb-690b-40a2-8f09-0f026692a649`. No actual fantasy results were read or used.

## 2. Changes since overnight

[The hashed change ledger](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/changes_before_selection.json) was frozen at **2026-10-01T10:50:09.457271+00:00**, before discovery/portfolio selection. It records 149 field differences with canonical identity, old/new values, source, observation and expected effect. Complete field differences include diagnostic ownership and source-derived availability changes; they are not all material football changes.

| Input | Overnight | Game day | Consequence |
| --- | --- | --- | --- |
| DK file observation | September 29 | October 1 official download | Salary/slot freshness gap resolved |
| Dowdle / Wallace DK flag | Q | OUT | Confirms exclusions already justified by official report |
| Projection output rows | 47 | 45 | Two OUT salary rows no longer get projections; no reactivation |
| Ownership slots | 100; KC missing | 102; complete | Still diagnostic due unchanged poor calibration |
| PIT spread / total | −2.5 / 38.5 | −2.5 / 38.5 | No market-driven change |
| 20:00 / 23:00 precipitation probability | 4% / 1% | 6% / 44% | Recheck late showers; no manual projection patch |
| Primary captains | Metcalf / Watson / Jeudy | Metcalf / Watson / Jeudy | Re-earned in fresh joint solve |
| Ten-entry CPT allocation | Metcalf 5, Watson 1, Rodgers 1, Boston 2, Wilson 1 | Metcalf 6, Watson 1, Rodgers 1, Boston 1, Wilson 1 | Fresh ten-entry sensitivity differs |

No new official fantasy-player Q/OUT designation, new starter, active-roster transaction or published game-day elevation was found. The official injury designations were reconfirmed; final inactives remain unknown. Small projection changes are outputs of the normal rebuild on the changed eligible target pool and refreshed source inputs, not manual role or projection edits.

## 3. Entry readiness

| Gate | Result | Evidence / remaining condition |
| --- | --- | --- |
| Fresh DK salaries / IDs | PASS | 102 exact native-slot/canonical checks; public official download disclosed |
| Identity integrity | PASS | 51/51 DK identities; FD-only unresolved row isolated |
| Projection coverage | PASS with warning | 45/45 eligible salary rows have fresh projection records; 31 positive; all 23 prepared players positive |
| Injury freshness | PASS for morning | Fresh official final designations + Operations FD confirmation |
| Final game-day inactives | PENDING — BLOCKS ENTRY | No final active/inactive assertion at 06:43 source observation |
| Starting QB confidence | PASS, recheck at lock | Rodgers and Watson remain first on fresh official depth charts |
| Market / weather | PASS for morning | Fresh primary snapshots; late shower risk warrants final refresh |
| Role evidence | CONDITIONAL | Official depth supports primary skill roles; workload remains uncertain until game-day confirmation |
| Candidate legality / CPT-FLEX coverage | PASS | 770 legal candidates; all 23 viable players have CPT and FLEX coverage |
| Ownership quality | UNTRUSTED — NONBLOCKING | Complete coverage does not fix Showdown calibration; uniformly masked before MILP and selection |
| Final tests / preservation | PASS | 115 tests; 90 protected hashes and 75 Classic configs unchanged |

The existing application Showdown-GPP gate reports “ready with warning” (96/100), with positive-projection coverage its warning. The additional task-specific final-inactives/freshness gate is stricter, so **ENTRY READY remains NO**. Overall readiness failures for Classic/replay are irrelevant to this upcoming Showdown slate; actual-results absence is expected.

Ownership: CPT held-out MAE 12.92, bias +11.57; FLEX MAE 7.59, bias -3.99. Raw slate totals are CPT **260.87%** and FLEX **380.73%**, versus slot totals 100%/500%. Raw estimates remain frozen as diagnostics. They are uniformly unavailable **before** MILP capture and selector scoring, using the overnight reliability policy. Fixed selector weights and production ownership code/config are unchanged.

## 4. Final injury / inactive status

| Team | Player | Newest verified designation | Implication |
| --- | --- | --- | --- |
| PIT | Rico Dowdle | OUT — toe | Excluded; FD O and fresh DK OUT agree |
| PIT | Joey Porter Jr. | OUT | Defensive matchup context |
| PIT | Jalen Ramsey | QUESTIONABLE — wrist | Await final availability |
| PIT | Brandin Echols | QUESTIONABLE — concussion | Protocol clearance does not remove Q designation |
| CLE | Tylan Wallace | OUT — knee | Excluded; FD O and fresh DK OUT agree |
| CLE | Elgton Jenkins | OUT — concussion | Luke Wypler replacement expected; matchup context |
| CLE | Teven Jenkins | OUT — back | Offensive-line matchup context |

These designations are supported by the [Steelers final injury report](https://www.steelers.com/news/week-4-injury-report-browns) and [Browns final injury report](https://www.clevelandbrowns.com/news/elgton-jenkins-out-for-week-4-against-the-steelers-injury-report), recaptured this morning. Official inactives are not yet published. PIT’s latest listed transaction remains September 26 (Homer active, Dunker IR); CLE’s September 29 changes concern practice-squad/IR personnel and add no new DK-eligible offensive elevation. Nichols has no newly verified elevation.

## 5. Market / weather

The fresh [DraftKings market](https://dknetwork.draftkings.com/moneyline-total-spread/) remains PIT −2.5, total 38.5; implied totals PIT **20.5**, CLE **18.0**. Observation time is recorded in the capture manifest; the provider supplies no independently verifiable update timestamp.

| Local hour | Overnight temperature / wind / rain | Fresh temperature / wind / rain |
| --- | --- | --- |
| 20:00 | 76°F / 9 mph / 4% | 77°F / 9 mph / 6% |
| 21:00 | 76°F / 9 mph / 4% | 76°F / 9 mph / 9% |
| 22:00 | 75°F / 8 mph / 0% | 75°F / 9 mph / 20% |
| 23:00 | 75°F / 8 mph / 1% | 75°F / 9 mph / 44% |

The fresh [NWS hourly forecast](https://api.weather.gov/gridpoints/CLE/83,65/forecast/hourly), updated 07:46 UTC, shows modest wind but a rising late-game rain chance. Forecast probability is not a confirmed rain amount or a realized game condition. NWS evidence informs the watch list; the existing model rebuild was used without inventing a weather adjustment.

## 6. Role changes

| Player | Fresh official role check | Lag snaps | Model carries / targets |
| --- | --- | --- | --- |
| Jaylen Warren | First RB; Dowdle OUT. Prior official report supports focal workload, but no new exact carry/snap guarantee. | 0.353 | 16.16 / 3.93 |
| Travis Homer | On active roster after Sep 26; fourth depth RB. Dressing and meaningful touches remain unconfirmed. | 0.000 | 0.91 / 0.00 |
| Roman Wilson | First depth WR; current starting role retained. | 0.377 | — / 4.80 |
| Pat Freiermuth | First depth TE group alongside Washington; role retained. | 0.707 | — / 4.77 |
| DK Metcalf | First depth WR; no new injury designation. | 0.877 | — / 8.76 |
| Deshaun Watson | First depth QB; no new starter change. | 0.790 | — / — |
| Quinshon Judkins | First RB; Sampson IR, existing primary workload retained. | 0.570 | 9.19 / 3.46 |
| Jerry Jeudy | First depth WR; no new injury designation. | 0.817 | — / 3.61 |
| Denzel Boston | First depth WR; rookie role supported, performance uncertainty persists. | 0.920 | — / 4.31 |
| KC Concepcion Jr. | First depth WR; return assignment alone is not the justification. | 0.690 | — / 4.13 |
| Harold Fannin Jr. | First depth TE; role retained. | 0.637 | — / 3.05 |

Source: fresh [PIT official depth chart](https://www.steelers.com/team/depth-chart/) and [CLE Week 4 official depth chart](https://www.clevelandbrowns.com/news/browns-announce-unofficial-depth-chart-for-week-4-vs-the-steelers), roster and transaction captures. Recent snaps/carries/targets are historical/model evidence, not newly announced game-day workload promises. Fresh context has 36 active-roster/DST assumptions and 15 unavailable/non-active players; availability=1 means pending-inactives eligibility. No invented routes/snaps/volume were submitted.

## 7. Projection changes

| Player | Old mean | New mean | Old P90 | New P90 | Mean change |
| --- | --- | --- | --- | --- | --- |
| Jerry Jeudy | 6.243 | 6.237 | 17.371 | 17.364 | -0.006 |
| Eli Heidenreich | 1.555 | 1.742 | 3.771 | 3.957 | 0.186 |
| Darnell Washington | 3.669 | 3.647 | 8.287 | 8.265 | -0.022 |
| Carsen Ryan | 0.963 | 0.974 | 5.580 | 5.591 | 0.011 |
| Quinshon Judkins | 10.424 | 10.471 | 21.891 | 21.938 | 0.047 |
| Michael Pittman Jr. | 7.190 | 7.183 | 18.318 | 18.311 | -0.007 |
| Denzel Boston | 9.606 | 9.682 | 22.453 | 22.528 | 0.075 |
| KC Concepcion Jr. | 7.338 | 7.392 | 17.167 | 17.221 | 0.054 |
| Germie Bernard | 6.760 | 7.228 | 12.712 | 13.180 | 0.468 |
| Blake Whiteheart | 2.072 | 2.085 | 6.689 | 6.702 | 0.013 |
| Roman Wilson | 7.031 | 6.988 | 12.983 | 12.940 | -0.043 |
| Robert Tonyan | 1.194 | 1.181 | 2.299 | 2.287 | -0.012 |
| Isaiah Bond | 1.825 | 1.824 | 7.776 | 7.776 | -0.000 |
| Travis Homer | 0.928 | 0.921 | 3.144 | 3.136 | -0.008 |
| Raheim Sanders | 4.027 | 4.022 | 12.048 | 12.044 | -0.005 |
| Pat Freiermuth | 8.528 | 8.382 | 15.646 | 15.500 | -0.146 |
| Harold Fannin Jr. | 7.875 | 7.891 | 14.993 | 15.010 | 0.017 |
| Malachi Corley | 1.420 | 1.419 | 7.372 | 7.371 | -0.001 |

Normal production feature build wrote 51 Thursday rows; prediction produced 45 eligible records. [Refresh lineage](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/input_refresh_lineage.json), [complete frozen pool](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/refreshed_database_freeze.json), and [all old/new fields](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/changes_before_selection.json) preserve the exact run and evidence. Mean/P90 for Metcalf, Watson, Rodgers and Warren are unchanged. Dowdle/Wallace now lack a projection join because salary status excludes them; raw NULL availability is not clearance—the frozen context still says zero and production preparation excludes both.

## 8. Candidate coverage

Initial broad discovery retained **692** unique assignments; fully rebuilt PIT/CLE conditional objectives extended the identical fresh universe to **770** (overnight 769). Exact baseline re-evaluation of overnight primary entries was included before the final common-universe ranking. All 770 pass six distinct canonical identities, one CPT/five FLEX, ≤$50,000, both teams and positive prepared availability.

Architecture and depths are unchanged: global ceiling 40/mean 25; each viable CPT ceiling 20/mean 5; each forced FLEX 3; 3–3/4–2/5–1, QB+receiver/RB+DST/K+DST, both single-QB directions and dual-QB constructions; approximate proposal scenarios followed by complete conditional MILP rebuilding and exact baseline rescoring. The old 30-candidate production control and optimizer HTML were not regenerated.

| Viable player | CPT coverage | FLEX coverage |
| --- | --- | --- |
| Jerry Jeudy | 30 | 336 |
| Eli Heidenreich | 33 | 3 |
| Darnell Washington | 31 | 4 |
| Quinshon Judkins | 31 | 331 |
| Michael Pittman Jr. | 30 | 121 |
| Denzel Boston | 47 | 360 |
| KC Concepcion Jr. | 28 | 119 |
| Germie Bernard | 28 | 52 |
| Blake Whiteheart | 31 | 3 |
| Deshaun Watson | 31 | 600 |
| Roman Wilson | 30 | 40 |
| Browns | 27 | 94 |
| Travis Homer | 32 | 3 |
| Jaleel McLaughlin | 34 | 43 |
| Chris Boswell | 34 | 30 |
| Raheim Sanders | 34 | 19 |
| Pat Freiermuth | 29 | 71 |
| Andre Szmyt | 32 | 74 |
| Harold Fannin Jr. | 31 | 29 |
| DK Metcalf | 79 | 528 |
| Steelers | 25 | 94 |
| Jaylen Warren | 36 | 443 |
| Aaron Rodgers | 27 | 453 |

Zero coverage: **none among all 23 production-prepared players**, either as CPT or FLEX. Both QB directions, both teams and all requested construction families were searched. Remaining salary players are explicitly removed by existing availability, backup-QB or positive-opportunity gates. The universe is broad research enumeration, not an exhaustive proof over every DK-legal roster; the existing ≥1 starting-QB/football rules still apply.

| Discovery family | First unique attribution | Within .10 first attribution | Search seconds |
| --- | --- | --- | --- |
| captain_ceiling | 409 | 145 | 75.70 |
| captain_mean | 43 | 7 | 7.76 |
| conditional_exact | 78 | 10 | 17.98 |
| construction | 15 | 6 | 5.34 |
| forced_flex | 19 | 11 | 4.94 |
| global_ceiling | 40 | 40 | 5.93 |
| global_mean | 22 | 19 | 4.51 |
| qb_construction | 7 | 1 | 4.26 |
| scenario | 105 | 8 | 6.88 |
| structure | 32 | 1 | 5.58 |

Discovery plus exact conditional extension runtime **146.80 seconds**; feature/model fitting and report work are separate. Attribution follows discovery order and understates redundant supporting sources; it is not an ablation claim. All source tags and per-search runtime are preserved in [quality_shadow.json](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/quality_shadow.json).

## 9. CPT frontier

| CPT | Fresh best | Fresh gap | Old local gap | Fresh depth .05/.10/.15/.20/.30 | Old depth .05/.10/.15/.20/.30 | Lineup mean / P90 | CPT / lineup salary | Best thesis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DK Metcalf | 0.921925 | 0.000000 | 0.000000 | 18 / 40 / 62 / 77 / 79 | 16 / 39 / 64 / 79 / 80 | 64.19 / 136.10 | 13500 / 49300 | balanced competitive |
| Deshaun Watson | 0.917146 | 0.004779 | 0.004802 | 9 / 24 / 30 / 31 / 31 | 9 / 23 / 29 / 30 / 30 | 64.24 / 135.06 | 14100 / 49500 | balanced competitive |
| Aaron Rodgers | 0.906129 | 0.015796 | 0.015829 | 8 / 18 / 27 / 27 / 27 | 8 / 17 / 27 / 27 / 27 | 62.69 / 133.63 | 14700 / 49700 | balanced competitive |
| Denzel Boston | 0.905968 | 0.015957 | 0.016345 | 6 / 23 / 38 / 44 / 47 | 5 / 22 / 36 / 43 / 46 | 62.92 / 134.83 | 12000 / 48800 | balanced competitive |
| Jerry Jeudy | 0.900882 | 0.021043 | 0.022666 | 11 / 22 / 26 / 29 / 30 | 11 / 21 / 26 / 29 / 30 | 63.28 / 138.69 | 4500 / 49500 | CLE passing concentration |
| Jaylen Warren | 0.899878 | 0.022047 | 0.022311 | 3 / 21 / 31 / 36 / 36 | 3 / 21 / 30 / 36 / 36 | 65.76 / 134.44 | 14400 / 49600 | PIT rushing-led concentration |
| Michael Pittman Jr. | 0.895877 | 0.026048 | 0.027222 | 1 / 13 / 23 / 30 / 30 | 1 / 13 / 23 / 30 / 30 | 60.47 / 135.53 | 10500 / 49700 | balanced competitive |
| Pat Freiermuth | 0.883735 | 0.038190 | 0.037012 | 2 / 16 / 24 / 29 / 29 | 2 / 16 / 24 / 29 / 29 | 65.09 / 132.77 | 8400 / 49200 | PIT passing concentration |
| Quinshon Judkins | 0.882831 | 0.039094 | 0.039085 | 1 / 12 / 26 / 29 / 31 | 1 / 12 / 25 / 28 / 30 | 64.10 / 133.95 | 13200 / 50000 | balanced competitive |
| KC Concepcion Jr. | 0.876747 | 0.045178 | 0.046888 | 3 / 13 / 23 / 28 / 28 | 2 / 13 / 23 / 28 / 28 | 61.53 / 129.48 | 9600 / 49800 | balanced competitive |
| Roman Wilson | 0.874747 | 0.047178 | 0.047244 | 1 / 17 / 25 / 29 / 30 | 1 / 17 / 24 / 29 / 30 | 63.00 / 128.93 | 6000 / 46800 | PIT passing concentration |
| Andre Szmyt | 0.863128 | 0.058797 | 0.059463 | 0 / 9 / 23 / 27 / 32 | 0 / 10 / 24 / 28 / 33 | 64.37 / 129.10 | 6900 / 47700 | balanced competitive |
| Germie Bernard | 0.858642 | 0.063283 | 0.071365 | 0 / 13 / 22 / 25 / 28 | 0 / 8 / 20 / 24 / 28 | 64.77 / 132.41 | 4800 / 49800 | balanced competitive |
| Chris Boswell | 0.843316 | 0.078609 | 0.079287 | 0 / 4 / 22 / 26 / 34 | 0 / 3 / 20 / 25 / 33 | 62.27 / 127.00 | 7800 / 48600 | balanced competitive |
| Harold Fannin Jr. | 0.835616 | 0.086309 | 0.087146 | 0 / 3 / 18 / 29 / 31 | 0 / 3 / 18 / 30 / 32 | 59.03 / 126.36 | 11100 / 49300 | balanced competitive |
| Darnell Washington | 0.818219 | 0.103706 | 0.104648 | 0 / 0 / 15 / 25 / 31 | 0 / 0 / 15 / 25 / 31 | 59.15 / 121.77 | 5400 / 49600 | PIT passing concentration |
| Jaleel McLaughlin | 0.811880 | 0.110045 | 0.111404 | 0 / 0 / 6 / 20 / 31 | 0 / 0 / 6 / 20 / 31 | 60.43 / 131.18 | 600 / 46400 | balanced competitive |
| Browns | 0.792022 | 0.129903 | 0.131731 | 0 / 0 / 4 / 19 / 27 | 0 / 0 / 4 / 19 / 27 | 62.67 / 130.46 | 7200 / 49600 | CLE passing concentration |
| Blake Whiteheart | 0.791511 | 0.130414 | 0.131966 | 0 / 0 / 2 / 14 / 29 | 0 / 0 / 2 / 14 / 29 | 59.09 / 124.73 | 2400 / 48200 | balanced competitive |
| Raheim Sanders | 0.790021 | 0.131904 | 0.132522 | 0 / 0 / 5 / 21 / 31 | 0 / 0 / 6 / 21 / 31 | 58.55 / 127.58 | 6600 / 47400 | balanced competitive |
| Eli Heidenreich | 0.772577 | 0.149348 | 0.153154 | 0 / 0 / 1 / 9 / 26 | 0 / 0 / 0 / 8 / 26 | 58.58 / 120.61 | 3300 / 49100 | PIT rushing-led concentration |
| Steelers | 0.767252 | 0.154673 | 0.154809 | 0 / 0 / 0 / 9 / 25 | 0 / 0 / 0 / 9 / 25 | 60.70 / 126.02 | 7500 / 49500 | PIT passing concentration |
| Travis Homer | 0.761989 | 0.159936 | 0.161243 | 0 / 0 / 0 / 6 / 24 | 0 / 0 / 0 / 6 / 24 | 57.35 / 119.38 | 3900 / 49700 | PIT rushing-led concentration |

Old and new selector scores use their own universe normalization. The local frontier gaps/counts are diagnostic comparisons; cross-day score subtraction does not measure a lineup improvement. Portfolio D below was re-solved and rescored on today’s exact model and common normalization. CPT depth is discovered depth, not exhaustive recall.

### QB CPT versus FLEX

| QB | Historical carries/game | CPT premium | Best CPT | Best FLEX | CPT opportunity cost | Primary verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Aaron Rodgers | 1.333 | $4,900 | 0.906129 | 0.921925 | 0.015796 | NO — non-rushing CPT rotation adds no new thesis |
| Deshaun Watson | 5.000 | $4,700 | 0.917146 | 0.921925 | 0.004779 | YES — balanced mobile-QB path |

Watson retains the existing mobile-QB classification through five lag carries per game, making the $4,700 premium defensible. Rodgers remains non-rushing at 1.333 carries per game; his $4,900 premium costs 0.015796 selector versus the best FLEX construction, and the best Rodgers-CPT entry repeats the balanced six-player core. His CPT bonus adds 4.61 mean/10.06 marginal P90 before roster opportunity costs. He is a ten-entry sensitivity, not a primary captain. No new rushing or starting-status evidence changes either classification.

## 10. Thesis frontier

| Actual roster thesis | Peak / gap | Depth .05/.10/.15/.20/.30 | CPT options |
| --- | --- | --- | --- |
| balanced competitive | 0.921925 / 0.000000 | 35 / 121 / 187 / 244 / 294 | Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Darnell Washington, Denzel Boston, Deshaun Watson, Eli Heidenreich, Germie Bernard, Harold Fannin Jr., Jaleel McLaughlin, Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, Raheim Sanders, Roman Wilson, Steelers, Travis Homer |
| PIT passing concentration | 0.917724 / 0.004201 | 14 / 53 / 117 / 152 / 158 | Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Chris Boswell, DK Metcalf, Darnell Washington, Deshaun Watson, Germie Bernard, Jaleel McLaughlin, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Raheim Sanders, Roman Wilson, Steelers |
| CLE passing concentration | 0.901094 / 0.020831 | 12 / 61 / 109 / 135 / 156 | Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Denzel Boston, Deshaun Watson, Eli Heidenreich, Harold Fannin Jr., Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Steelers, Travis Homer |
| PIT rushing-led concentration | 0.899878 / 0.022047 | 2 / 5 / 11 / 21 / 32 | Eli Heidenreich, Jaylen Warren, Travis Homer |
| CLE rushing-led concentration | 0.862000 / 0.059925 | 0 / 8 / 24 / 49 / 66 | Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders |
| defensive/kicking | 0.808998 / 0.112927 | 0 / 0 / 5 / 14 / 33 | Andre Szmyt, Browns, Chris Boswell, Steelers |
| PIT rushing/control | 0.771287 / 0.150638 | 0 / 0 / 0 / 3 / 3 | Eli Heidenreich, Jaylen Warren, Travis Homer |
| CLE rushing/control | 0.727127 / 0.194798 | 0 / 0 / 0 / 1 / 5 | Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders |

Direct overnight/fresh comparison below uses local peak gaps and discovered counts. Allocation is always PIT–CLE; dependencies are the four most frequent players within each full thesis family. A CPT roster alone does not imply a separate thesis.

| Thesis | Old → fresh peak local gap | Old → fresh total depth | Old → fresh allocations | Old → fresh key dependencies | Old → fresh CPT options |
| --- | --- | --- | --- | --- | --- |
| CLE passing concentration | 0.022092 → 0.020831 | 157 → 157 | {'1-5': 57, '2-4': 100} → {'1-5': 58, '2-4': 99} | Deshaun Watson 157/157, Denzel Boston 128/157, Jerry Jeudy 114/157, DK Metcalf 105/157 → Deshaun Watson 157/157, Denzel Boston 129/157, Jerry Jeudy 114/157, DK Metcalf 106/157 | Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Denzel Boston, Deshaun Watson, Eli Heidenreich, Harold Fannin Jr., Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Steelers, Travis Homer → Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Denzel Boston, Deshaun Watson, Eli Heidenreich, Harold Fannin Jr., Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Steelers, Travis Homer |
| CLE rushing-led concentration | 0.061177 → 0.059925 | 67 → 68 | {'1-5': 22, '2-4': 45} → {'1-5': 22, '2-4': 46} | Deshaun Watson 65/67, Quinshon Judkins 57/67, DK Metcalf 55/67, Denzel Boston 42/67 → Deshaun Watson 66/68, Quinshon Judkins 58/68, DK Metcalf 55/68, Denzel Boston 43/68 | Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders → Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders |
| CLE rushing/control | 0.196060 → 0.194798 | 9 → 9 | {'3-3': 9} → {'3-3': 9} | Browns 9/9, DK Metcalf 9/9, Aaron Rodgers 9/9, Quinshon Judkins 7/9 → Browns 9/9, DK Metcalf 9/9, Aaron Rodgers 9/9, Quinshon Judkins 7/9 | Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders → Jaleel McLaughlin, Quinshon Judkins, Raheim Sanders |
| PIT passing concentration | 0.004441 → 0.004201 | 156 → 158 | {'4-2': 90, '5-1': 66} → {'4-2': 91, '5-1': 67} | Aaron Rodgers 156/156, DK Metcalf 142/156, Jaylen Warren 126/156, Deshaun Watson 75/156 → Aaron Rodgers 158/158, DK Metcalf 144/158, Jaylen Warren 128/158, Deshaun Watson 76/158 | Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Chris Boswell, DK Metcalf, Darnell Washington, Deshaun Watson, Germie Bernard, Jaleel McLaughlin, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Raheim Sanders, Roman Wilson, Steelers → Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Chris Boswell, DK Metcalf, Darnell Washington, Deshaun Watson, Germie Bernard, Jaleel McLaughlin, Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, Raheim Sanders, Roman Wilson, Steelers |
| PIT rushing-led concentration | 0.022311 → 0.022047 | 41 → 41 | {'4-2': 23, '5-1': 18} → {'4-2': 23, '5-1': 18} | Jaylen Warren 39/41, Aaron Rodgers 37/41, DK Metcalf 36/41, Deshaun Watson 27/41 → Jaylen Warren 39/41, DK Metcalf 37/41, Aaron Rodgers 37/41, Deshaun Watson 27/41 | Eli Heidenreich, Jaylen Warren, Travis Homer → Eli Heidenreich, Jaylen Warren, Travis Homer |
| PIT rushing/control | 0.151670 → 0.150638 | 9 → 9 | {'3-3': 9} → {'3-3': 9} | Deshaun Watson 9/9, Steelers 9/9, Jaylen Warren 9/9, Denzel Boston 8/9 → Deshaun Watson 9/9, Steelers 9/9, Jaylen Warren 9/9, Denzel Boston 8/9 | Eli Heidenreich, Jaylen Warren, Travis Homer → Eli Heidenreich, Jaylen Warren, Travis Homer |
| balanced competitive | 0.000000 → 0.000000 | 297 → 295 | {'1-5': 5, '2-4': 58, '3-3': 203, '4-2': 29, '5-1': 2} → {'1-5': 5, '2-4': 58, '3-3': 201, '4-2': 29, '5-1': 2} | Deshaun Watson 270/297, DK Metcalf 227/297, Aaron Rodgers 216/297, Jaylen Warren 160/297 → Deshaun Watson 268/295, DK Metcalf 225/295, Aaron Rodgers 213/295, Jaylen Warren 160/295 | Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Darnell Washington, Denzel Boston, Deshaun Watson, Eli Heidenreich, Germie Bernard, Harold Fannin Jr., Jaleel McLaughlin, Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, Raheim Sanders, Roman Wilson, Steelers, Travis Homer → Aaron Rodgers, Andre Szmyt, Blake Whiteheart, Browns, Chris Boswell, DK Metcalf, Darnell Washington, Denzel Boston, Deshaun Watson, Eli Heidenreich, Germie Bernard, Harold Fannin Jr., Jaleel McLaughlin, Jaylen Warren, Jerry Jeudy, KC Concepcion Jr., Michael Pittman Jr., Pat Freiermuth, Quinshon Judkins, Raheim Sanders, Roman Wilson, Steelers, Travis Homer |
| defensive/kicking | 0.114305 → 0.112927 | 33 → 33 | {'1-5': 3, '2-4': 5, '3-3': 15, '4-2': 7, '5-1': 3} → {'1-5': 3, '2-4': 5, '3-3': 15, '4-2': 7, '5-1': 3} | DK Metcalf 29/33, Jaylen Warren 26/33, Deshaun Watson 25/33, Andre Szmyt 19/33 → DK Metcalf 29/33, Jaylen Warren 26/33, Deshaun Watson 25/33, Andre Szmyt 19/33 | Andre Szmyt, Browns, Chris Boswell, Steelers → Andre Szmyt, Browns, Chris Boswell, Steelers |

Theses are derived from actual allocation, QB/receiver combinations, RB/DST and kicking construction; changing CPT alone does not create an independent thesis. The three supported primary paths remain PIT passing concentration, balanced competitive and CLE passing concentration. Rushing/control and defensive/kicking branches are present as sensitivity candidates, without forcing them into the primary three. Complete allocations, dependencies and prior statistics remain in the linked decision/overnight audit artifacts.

## 11. Cheap-player review

| Cheap player | FLEX salary | Mean / P90 | Recent snaps | Best containing rank / gap | Cost to avoid vs global | Role gate |
| --- | --- | --- | --- | --- | --- | --- |
| Jerry Jeudy | 3000 | 6.24 / 17.36 | 0.817 | 1 / 0.000000 | 0.036386 | First WR; 81.7% recent snaps; supported despite low DK price. Primary eligible pending inactives. |
| Roman Wilson | 4000 | 6.99 / 12.94 | 0.377 | 2 / 0.004201 | 0.000000 | First WR; 37.7% recent snaps and positive target evidence; supported secondary passing role. Primary eligible pending inactives. |
| Germie Bernard | 3200 | 7.23 / 13.18 | 0.040 | 15 / 0.024436 | 0.000000 | Second behind Pittman; 4% recent snaps; model targets include salary-based fallback. Fragile, not primary; one diagnostic ten entry. |
| Darnell Washington | 3600 | 3.65 / 8.26 | 0.487 | 33 / 0.037312 | 0.000000 | Listed in first TE group; supported role but lower target concentration. No need to force into primary. |
| Jaleel McLaughlin | 400 | 2.98 / 11.00 | 0.197 | 77 / 0.055691 | 0.000000 | Active since Sep 15; fourth depth RB; 19.7% recent snaps and modest opportunity. $400 alone is insufficient; avoid primary. |
| Blake Whiteheart | 1600 | 2.09 / 6.70 | 0.553 | 143 / 0.073630 | 0.000000 | Second TE; recent snaps do not guarantee targets; uncertain passing role. Avoid primary. |
| Eli Heidenreich | 2200 | 1.74 / 3.96 | 0.040 | 209 / 0.092538 | 0.000000 | Third depth RB; 4% recent snaps. Dowdle OUT does not prove touches; avoid primary. |
| Travis Homer | 2600 | 0.92 / 3.14 | 0.000 | 247 / 0.099560 | 0.000000 | New active-roster RB but zero recent snaps; no guaranteed game-day role. Avoid primary. |

All active-roster labels above are pending official inactives. No newly activated minimum-salary player was found. No practice-squad, return-only or unsupported volume assumption justifies a primary punt. Jeudy and Wilson are inexpensive supported receivers; no fragile punt is in the primary three. Individual best containing/avoiding assignments are fully listed in the cheap section of the decision JSON. Avoidance costs use the same full-universe normalizers.

## 12. PIT decisive scenario

| Scenario comparison | CPT | Allocation | Baseline rank / selector / gap | Conditional mean / P90 |
| --- | --- | --- | --- | --- |
| Best exact conditioned objective | DK Metcalf | 4–2 | 2 / 0.917724 / 0.004201 | 69.85 / 143.28 |
| Closest baseline dominant branch | DK Metcalf | 4–2 | 2 / 0.917724 / 0.004201 | 69.85 / 143.28 |

**CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.

**YES**, via the pass-led 4–2 Metcalf primary. Its fresh baseline gap is 0.004201 versus 0.004441 overnight. No forced 5–1 allocation is necessary. Warren volume and Rodgers/Metcalf/Wilson concentration are the dependencies.

Conditional values come from the existing margin/role conditioning method and complete rebuilt objective/correlation coefficients. Every retained roster is separately re-solved on the baseline MILP. No conditional mean is used as a baseline forecast, and no empirical probability of a 14+ win is asserted.

## 13. CLE decisive scenario

| Scenario comparison | CPT | Allocation | Baseline rank / selector / gap | Conditional mean / P90 |
| --- | --- | --- | --- | --- |
| Best exact conditioned objective | Denzel Boston | 5–1 | 139 / 0.849267 / 0.072658 | 67.66 / 148.19 |
| Closest baseline dominant branch | Jerry Jeudy | 4–2 | 12 / 0.900882 / 0.021043 | 67.04 / 146.92 |

**CPT Denzel Boston**; FLEX Jerry Jeudy, Quinshon Judkins, KC Concepcion Jr., Deshaun Watson, DK Metcalf.

**BORDERLINE** for a dedicated 14+ CLE win entry. The best conditioned branch remains Boston-CPT 5–1, baseline gap about 0.073 versus 0.075 overnight. The primary Jeudy 4–2 passing concentration offers a better baseline compromise; it does not require a 14+ win. CLE OL injuries and uncertain script limit the dedicated blowout claim.

Conditional values come from the existing margin/role conditioning method and complete rebuilt objective/correlation coefficients. Every retained roster is separately re-solved on the baseline MILP. No conditional mean is used as a baseline forecast, and no empirical probability of a 14+ win is asserted.

## 14. Core-dependence sensitivity

Each comparison retains the same .10 frontier eligibility, distinct CPTs, distinct actual theses, maximum four shared players and existing fragile exposure limits. The 100% solve restricts all three entries to contain the named player; the alternative changes only that player’s maximum to two. Three entries remain feasible for every test. Costs are sums across entries, not independent portfolio quantiles.

| Core | 100% total selector | ≤2/3 selector | Selector cost / % | Mean cost | P90 cost | Alternative CPTs | Thesis effect |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DK Metcalf | 2.719396 | 2.713824 | 0.005571 / 0.205% | 4.323 | 5.170 | DK Metcalf, Denzel Boston, Jerry Jeudy | Preserves three thesis families |
| Deshaun Watson | 2.719396 | 2.657382 | 0.062014 / 2.280% | 4.550 | 10.198 | DK Metcalf, Deshaun Watson, Jaylen Warren | CLE passing replaced by PIT rushing |
| Jerry Jeudy | 2.719396 | 2.695352 | 0.024043 / 0.884% | 5.990 | 9.429 | DK Metcalf, Jerry Jeudy, KC Concepcion Jr. | Preserves three thesis families |

Metcalf is the affordable diversification lever: 0.205% total selector loss, but 4.32 total mean and 5.17 summed P90 points sacrificed. Jeudy costs 0.884%; Watson 2.280% and changes the thesis set. The quality-maximizing default keeps all three core players; no exposure preference/weight was silently added. The Metcalf ≤2/3 alternative is a concrete choice if lowering shared dependence is worth the stated forecast cost. It also swaps Watson CPT for Boston CPT.

**DK Metcalf ≤2/3 alternative**, fresh ranks [2, 12, 21]:

- #2: **CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.
- #12: **CPT Jerry Jeudy**; FLEX Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Aaron Rodgers.
- #21: **CPT Denzel Boston**; FLEX Jerry Jeudy, Deshaun Watson, Pat Freiermuth, Jaylen Warren, Aaron Rodgers.

**Deshaun Watson ≤2/3 alternative**, fresh ranks [2, 3, 243]:

- #2: **CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.
- #3: **CPT Deshaun Watson**; FLEX Jerry Jeudy, Denzel Boston, Pat Freiermuth, DK Metcalf, Aaron Rodgers.
- #243: **CPT Jaylen Warren**; FLEX Jerry Jeudy, Michael Pittman Jr., Pat Freiermuth, DK Metcalf, Aaron Rodgers.

**Jerry Jeudy ≤2/3 alternative**, fresh ranks [2, 12, 51]:

- #2: **CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.
- #12: **CPT Jerry Jeudy**; FLEX Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Aaron Rodgers.
- #51: **CPT KC Concepcion Jr.**; FLEX Denzel Boston, Deshaun Watson, Roman Wilson, DK Metcalf, Aaron Rodgers.

## 15. Final 3-entry recommendation

**Provisional quality recommendation: retain Metcalf / Watson / Jeudy**, contingent on the final active/role/market/weather refresh. The fresh unconstrained and captain-only comparators confirm the thesis solve is paying a measured quality cost, rather than mechanically choosing a third CPT.

| Comparison | Fresh ranks | Total selector | Cost vs A | Total mean | Summed P90 | Theses |
| --- | --- | --- | --- | --- | --- | --- |
| A_unconstrained | [1, 2, 3] | 2.756795 | 0.000000 | 194.05 | 406.15 | PIT passing concentration; balanced competitive |
| B_captain_only | [1, 3, 5] | 2.745199 | 0.011596 | 191.11 | 404.79 | balanced competitive |
| C_primary | [2, 3, 35] | 2.719396 | 0.037399 | 196.42 | 412.58 | CLE passing concentration; PIT passing concentration; balanced competitive |
| D_overnight_on_fresh_model | [2, 3, 35] | 2.719396 | 0.037399 | 196.42 | 412.58 | CLE passing concentration; PIT passing concentration; balanced competitive |

A means distinct CPT/FLEX assignments; changing CPT can still preserve the same six players. B’s three captains rotate within the same six-player balanced core (six shared). C costs **1.357%** selector versus A while delivering three actual thesis families and ≤4 shared. D is exactly the overnight three re-solved on today’s model and normalization, matching C. This is a genuine refreshed equality, not subtraction of scores from two different universes.

| Entry | CPT | Thesis | Selector | Gap | Mean | P90 | PIT-CLE | Salary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | DK Metcalf | PIT passing concentration | 0.917724 | 0.004201 | 65.62 | 134.99 | 4–2 | $49,300 |
| 2 | Deshaun Watson | balanced competitive | 0.917146 | 0.004779 | 64.24 | 135.06 | 3–3 | $49,500 |
| 3 | Jerry Jeudy | CLE passing concentration | 0.884526 | 0.037399 | 66.57 | 142.54 | 2–4 | $49,300 |

**Entry 1**: **CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.

| Slot | Player | Fresh native DK slot ID | Salary |
| --- | --- | --- | --- |
| CPT | DK Metcalf | 44315946 | $13,500 |
| FLEX | Jerry Jeudy | 44315917 | $3,000 |
| FLEX | Deshaun Watson | 44315894 | $9,400 |
| FLEX | Roman Wilson | 44315914 | $4,000 |
| FLEX | Jaylen Warren | 44315893 | $9,600 |
| FLEX | Aaron Rodgers | 44315892 | $9,800 |

**Entry 2**: **CPT Deshaun Watson**; FLEX Jerry Jeudy, Denzel Boston, Pat Freiermuth, DK Metcalf, Aaron Rodgers.

| Slot | Player | Fresh native DK slot ID | Salary |
| --- | --- | --- | --- |
| CPT | Deshaun Watson | 44315945 | $14,100 |
| FLEX | Jerry Jeudy | 44315917 | $3,000 |
| FLEX | Denzel Boston | 44315897 | $8,000 |
| FLEX | Pat Freiermuth | 44315908 | $5,600 |
| FLEX | DK Metcalf | 44315895 | $9,000 |
| FLEX | Aaron Rodgers | 44315892 | $9,800 |

**Entry 3**: **CPT Jerry Jeudy**; FLEX Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren.

| Slot | Player | Fresh native DK slot ID | Salary |
| --- | --- | --- | --- |
| CPT | Jerry Jeudy | 44315968 | $4,500 |
| FLEX | Quinshon Judkins | 44315896 | $8,800 |
| FLEX | Denzel Boston | 44315897 | $8,000 |
| FLEX | Deshaun Watson | 44315894 | $9,400 |
| FLEX | DK Metcalf | 44315895 | $9,000 |
| FLEX | Jaylen Warren | 44315893 | $9,600 |

| Entry pair | Shared players |
| --- | --- |
| 1 / 2 | 4 |
| 1 / 3 | 4 |
| 2 / 3 | 4 |

| Player | Exposure |
| --- | --- |
| DK Metcalf | 3/3 |
| Deshaun Watson | 3/3 |
| Jerry Jeudy | 3/3 |
| Aaron Rodgers | 2/3 |
| Denzel Boston | 2/3 |
| Jaylen Warren | 2/3 |
| Pat Freiermuth | 1/3 |
| Quinshon Judkins | 1/3 |
| Roman Wilson | 1/3 |

Captain allocation: one Metcalf, one Watson, one Jeudy. Team allocation: 4 PIT/2 CLE, 3/3, 2 PIT/4 CLE. Fragile-role exposure **0/3**. Shared dependency remains Metcalf/Watson/Jeudy **3/3**; overlap alone does not remove this risk.

## 16. 10-entry sensitivity

Fresh supported-thesis diagnostic ranks **[1, 2, 3, 4, 5, 6, 11, 21, 32, 94]**, total selector **9.028998**. Same policy: .10 selector tolerance; CPT cap six; QB cap ten; other core cap eight; ≤$1,000 role cap four; at least one of each primary-supported thesis. The coverage requirement costs **0.004874** versus the unchanged quality-only ten solve.

| CPT | Overnight ten | Fresh ten |
| --- | --- | --- |
| Aaron Rodgers | 1 | 1 |
| DK Metcalf | 5 | 6 |
| Denzel Boston | 2 | 1 |
| Deshaun Watson | 1 | 1 |
| Roman Wilson | 1 | 1 |

| Fresh rank | CPT | Thesis | Selector | Allocation | Fragile role |
| --- | --- | --- | --- | --- | --- |
| 1 | DK Metcalf | balanced competitive | 0.921925 | {'CLE': 3, 'PIT': 3} | none |
| 2 | DK Metcalf | PIT passing concentration | 0.917724 | {'CLE': 2, 'PIT': 4} | none |
| 3 | Deshaun Watson | balanced competitive | 0.917146 | {'CLE': 3, 'PIT': 3} | none |
| 4 | DK Metcalf | balanced competitive | 0.917111 | {'CLE': 3, 'PIT': 3} | none |
| 5 | Aaron Rodgers | balanced competitive | 0.906129 | {'CLE': 3, 'PIT': 3} | none |
| 6 | DK Metcalf | balanced competitive | 0.906038 | {'CLE': 3, 'PIT': 3} | none |
| 11 | DK Metcalf | CLE passing concentration | 0.901094 | {'CLE': 4, 'PIT': 2} | none |
| 21 | Denzel Boston | balanced competitive | 0.895219 | {'CLE': 3, 'PIT': 3} | none |
| 32 | DK Metcalf | PIT passing concentration | 0.885539 | {'CLE': 2, 'PIT': 4} | Germie Bernard |
| 94 | Roman Wilson | PIT passing concentration | 0.861073 | {'CLE': 2, 'PIT': 4} | none |

Both QBs remain 10/10. Bernard appears in one diagnostic entry; this does not pass him into the primary three or create newly verified targets. No cheap punt is required by the primary recommendation. Rodgers CPT appears once in the ten diagnostic, where it deepens the balanced branch rather than adding an independent game thesis.

## 17. Remaining pre-lock watch items

At approximately **6:45 PM EDT (90 minutes before kickoff)**, inspect both official inactives, every primary player, Ramsey/Echols, Homer and any Nichols/other RB elevation. Reconfirm Rodgers/Watson starting roles, Warren’s backfield, CLE OL replacements and all primary receiver roles. Refresh the official DK file/IDs again if changed, the spread/total, and stadium wind/rain. A FanDuel blank injury flag or active roster alone is insufficient.

Append a new source/input freeze if anything changes; rebuild through existing services and re-run expanded discovery/joint selection. Preserve this morning’s decision and the overnight bundle. Entry readiness cannot be promoted until those outstanding checks pass. No automatic entry/export or future monitoring was enabled.

## 18. Tests and preservation

**115 relevant tests passed in 3.02 seconds**, including new native-slot verification failures, complete-but-uncalibrated ownership gating, exact three-entry core sensitivity/infeasibility handling, MILP/production objective agreement, legality, Showdown selectors/scenarios/contests, context, identity, source capture, prediction lineage and ownership. [Final test log](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/final_tests.log). Python compilation also passed.

The first broader test run exposed three pre-existing single-TE assumptions. Only those tests were aligned with the already-existing Showdown API policy that disables the single-TE restriction; generation/final validation now test multiple-TE legality. No production TE rule changed. The initial log is retained. The source-refresh script initially hit the existing injury-source uniqueness key; new game-day official evidence was appended under a separate source namespace before the model ran. No overnight snapshot was overwritten.

Preservation verification: **90 protected files unchanged**, including the complete overnight bundle/report and production code hashes; **75 saved Classic objective/constraint configs unchanged**; **zero** Thursday optimizer runs persisted. [Hash/config verification](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_gameday/20261001T103726Z/preservation_verified.json). Research scripts, tests, README/release notes and this new report are the only code/documentation changes for game-day analysis. No projection patches, selector/correlation/CPT/ownership parameter changes, Classic research changes or contest entries.

All summed player P90 values in this report are **sums of marginal P90s**, not simulated lineup/portfolio 90th-percentile outcomes. Selector is the existing heuristic quality score, not expected dollar profit. No realized-result tuning or evaluation was performed.

### ENTRY READY?

**NO.** Morning refresh is complete; final inactives/elevations and the last pre-lock source checks remain pending.

### What materially changed since last night?

Fresh official DK salaries/slot identities are now verified; Dowdle/Wallace are OUT in the DK file; FanDuel injuries are captured from Operations; normal projections were rebuilt; ownership coverage is complete but still unreliable; late-game rain chance rose. The preferred ten changes to Metcalf 6/Boston 1. The primary three do not change.

### Which CPTs are strongest now?

Metcalf leads the quality frontier; Watson is close. Rodgers ranks well in the same balanced core but does not earn a primary thesis slot. Jeudy is the preferred CLE passing-concentration captain; Boston is the leading alternative when capping Metcalf exposure. Full CPT depths are above.

### Which three CPTs should we use if entering exactly three?

**DK Metcalf / Deshaun Watson / Jerry Jeudy**, provisionally, subject to final checks.

### What are the exact three lineups?

1. **CPT DK Metcalf**; FLEX Jerry Jeudy, Deshaun Watson, Roman Wilson, Jaylen Warren, Aaron Rodgers.
2. **CPT Deshaun Watson**; FLEX Jerry Jeudy, Denzel Boston, Pat Freiermuth, DK Metcalf, Aaron Rodgers.
3. **CPT Jerry Jeudy**; FLEX Quinshon Judkins, Denzel Boston, Deshaun Watson, DK Metcalf, Jaylen Warren.

### What thesis does each represent?

1. PIT passing concentration, with 4–2 allocation.
2. Balanced competitive, 3–3 with both starting QBs.
3. CLE passing concentration, 4 CLE/2 PIT; asymmetric passing upside without requiring a blowout.

### What is pairwise overlap?

**4/6 for 1–2, 1–3 and 2–3.**

### Which players are 3/3?

**DK Metcalf, Deshaun Watson and Jerry Jeudy.**

### What would it cost to reduce each 3/3 core player to 2/3?

- **DK Metcalf:** 0.005571 total selector, 4.32 total mean, 5.17 summed P90 points. Thesis families preserved.
- **Deshaun Watson:** 0.062014 total selector, 4.55 total mean, 10.20 summed P90 points. CLE passing changes to PIT rushing.
- **Jerry Jeudy:** 0.024043 total selector, 5.99 total mean, 9.43 summed P90 points. Thesis families preserved.

Metcalf is the cheapest reduction; default quality preference retains the current three, with its complete cap alternative available for review.

### Does PIT decisive deserve an entry?

**YES**, through the supported Metcalf 4–2 pass-led primary; do not force 5–1.

### Does CLE decisive deserve an entry?

**BORDERLINE** for a dedicated 14+ blowout. Prefer the Jeudy passing-concentration primary.

### Are any fragile punts in the final three?

**NO.** Jeudy and Wilson are cheap but have supported receiving roles. Homer, Heidenreich, Bernard, McLaughlin and Whiteheart are absent. Final dressing status is still pending.

### Is Rodgers CPT justified in the primary three?

**NO.** Non-rushing evidence, salary premium and repeated balanced core do not materially improve the case.

### What game-day information is still unresolved?

Official inactives; Ramsey/Echols availability; any RB/other practice-squad elevation; Homer’s dressing/touch role; unexpected offensive scratches; final weather/market movement and starting confirmations. Ownership remains untrusted and nonblocking.

### What must be checked one final time approximately 90 minutes before kickoff?

At **6:45 PM EDT**, reconcile both official inactive lists and elevations against all 18 roster slots, verify the two starting QBs and backfields, inspect Ramsey/Echols and CLE OL replacements, and refresh DK IDs/salaries, spread/total and stadium rain/wind. Append fresh evidence and re-solve if anything material changes; only then declare ENTRY READY.
