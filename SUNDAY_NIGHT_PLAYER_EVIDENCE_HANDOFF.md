# Sunday Night player-evidence handoff

October 4, 2026; records inspected at 5:34 p.m. Eastern, outside sources reviewed afterward. **Next decision: verify the four supporting players' offensive roles and final availability before another user-run portfolio.** Canonical availability is missing because no pregame-context run has been supplied for this scope; no ingestion/join defect is proven.

Reference: saved run `a9c98d46-f854-4c55-a22c-89172c373314`, native DraftKings group **154098**, prepared job `6407651d-f9dd-4aa0-8914-59c18346ba16`, consumed projection `e5cf8edf-bd91-4f71-8323-dc6d8fd11480`, cutoff **5:23:13 p.m. Eastern**. Read the [actual HTML report](/Users/wones/Downloads/optimizer-report-2026-w4-sunday_night-a9c98d46.html) and [accepted prior review](/Users/wones/git/football_26/SUNDAY_NIGHT_SHOWDOWN_FIRST_RUN_REVIEW.md).

Accepted fixes stand: Coker is excluded by the questionable-player preference, with default availability, unchanged **14.45** model mean and no exclusion-driven redistribution. Recent market observation and prepared dependency lineage passed. No settings or saved lineups were changed.

## Selected-player checklist

All eleven identities are resolved in the saved native salary/player records. Their full canonical UUIDs, native aliases and salary row IDs are in [canonical-identities.json](/Users/wones/git/football_26/artifacts/sunday_night_player_evidence_handoff/canonical-identities.json). Target game **2026_04_DET_CAR / DET at CAR, October 4, 8:20 p.m. EDT**, agrees with the [official game center](https://www.panthers.com/gameday/2026/week4) and team depth charts; no game/team identity disagreement was found.

**For every row:** game-day active/inactive clearance is **unverified**; unrestricted workload and current numeric routes/targets/snaps forecasts are **missing**. The saved projection consumed historical role inputs and inferred QB starter IDs, but **none of the newly reviewed team pages or canonical practice context**. All eleven imported FanDuel designation fields are blank; blank is not healthy/active. Sources/times below distinguish dated facts from undated listings.

| Selected player / identity | Current designation evidence | Practice evidence | Offensive role evidence / remaining check |
| --- | --- | --- | --- |
| Amon-Ra St. Brown — DET WR | Not individually listed in L; clearance missing | Individual participation missing in L | DL lists first at WR; saved lagged three-game snap share 86.3%. Verify current role/limits. |
| Sam LaPorta — DET TE | Not individually listed in L; clearance missing | Individual participation missing in L | DL lists first TE; saved lagged snaps 90.3%. Verify current role/limits. |
| Bryce Young — CAR QB | P/PF: explicitly no Friday injury designation, knee noted | P: FULL Wed/Thu/Fri; retained S also FULL | DC lists first QB. Saved starter evidence is inferred, observed Oct 4 13:09:16Z, consumed; neither fact proves final clearance or unrestricted workload. |
| Ryan Fitzgerald — CAR K | Not individually listed in P; clearance missing | Individual participation missing | DC lists kicker; H documents four field goals last game. No current attempt-volume forecast. |
| Jared Goff — DET QB | Not individually listed in L; clearance missing | Individual participation missing in L | DL lists first QB. Same saved inferred-starter observation as Young, consumed; official game-day clearance missing. |
| Mitchell Evans — CAR TE | Not individually listed in P; clearance missing | Oct 1 practice photo in PF establishes presence, not FULL participation | DC lists second TE; H: 21 offensive snaps (27%), three catches in Week 3. Current receiving/blocking split missing. |
| Darren Waller — CAR TE | P/PF: explicitly no Friday injury designation, rest/toe noted | P: DNP Wed, FULL Thu/Fri; retained S FULL | DC lists third TE; H: 39 offensive snaps (51%), five catches in Week 3. Verify current routes and any toe/workload limitation. |
| John Metchie III — CAR WR | Not individually listed in P; clearance missing | Oct 1 photo in PF establishes presence, not FULL participation | DC lists behind Legette and at returner; R identifies him among available roster receivers after Legette's IR move. H: 43 offensive snaps (56%), two catches. Verify receiving role versus return duties. |
| Jahmyr Gibbs — DET RB | Not individually listed in L; clearance missing | Individual participation missing in L | DL lists first RB; saved lagged carry share 88.2%, snaps 75.3%. Verify current committee/limits. |
| Tommy Tremble — CAR TE | Not individually listed in P; clearance missing | Individual participation missing | DC lists first TE; H: 37 offensive snaps (48%), three catches in Week 3. First on chart does not establish receiving workload. |
| Jameson Williams — DET WR | Not individually listed in L; clearance missing | Individual participation missing in L | DL lists first at WR; saved lagged snaps 87.7%. Verify current role/limits. |

Source/time key (team-page times as displayed; underlying practice session times are not supplied):

- **P / PF:** [Panthers full injury table](https://www.panthers.com/team/injury-report/) is undated; corroborating [Friday Week 4 report](https://www.panthers.com/news/week-4-friday-injury-report-two-ruled-out-for-lions-game-xavier-legette-damien-lewis-questionable-jalen-coker) published **Oct 2, 12:30 p.m.**, with dated Oct 1 practice photo captions. These are newly reviewed; publication and photo times are not final clearance times.
- **L:** [Lions Friday report](https://www.detroitlions.com/news/lions-at-panthers-injury-report-oct-2-bartch-reed-wonnum), **Oct 2, 3:45 p.m.**; its three reported players do not provide individual practice/clearance facts for the selected Lions.
- **DC / DL:** [Panthers chart](https://www.panthers.com/team/depth-chart), linked by the [Week 4 release](https://www.panthers.com/news/panthers-release-depth-chart-ahead-of-week-4-of-the-2026-season-jaycee-horn), **Sep 29, 5:02 p.m.**; [Lions unofficial chart](https://www.detroitlions.com/team/depth-chart) has no original update timestamp. Dynamic chart contents cannot be backdated to an article's publication.
- **H:** [official Week 3 snap/count recap](https://www.panthers.com/news/inside-the-numbers-panthers-at-browns-in-week-3-brycen-tremayne-bryce-young-chuba-hubbard), **Sep 28, 6:23 a.m.**, about **Sep 27 at Cleveland**. Historical involvement only; consumption of this specific page is not demonstrated.
- **R:** [official roster update](https://www.panthers.com/news/panthers-place-wide-receiver-xavier-legette-on-injured-reserve-lions-sunday-night-football-jalen-coker-status), **Oct 3, 4 p.m.**: Legette IR, Reed elevated, Coker still questionable. It gives Metchie roster context, not guaranteed redistributed targets. Newly reviewed only.
- **S:** existing league-wide injury snapshot `d3350fc9-105b-5234-90c9-89a5b49f8563`, originally observed/captured **Oct 2, 9:24:40.772162 a.m. EDT**, basis `capture_clock`, upstream `nflreadpy://injuries/2026`. Publication/practice-session time unavailable. It exists in evidence storage, not consumed canonical context. Earlier snapshot shows Waller DNP; subsequent FULL evidence does not prove unrestricted workload.

## Supporting-player decisions, in priority order

1. **Waller, 4/5 entries:** saved FLEX mean/P90 **7.89/13.76**. Full practice and rising historical offensive involvement support a receiving path, but 80% exposure still depends on verifying his current routes, toe limitations and TE rotation. The user must decide whether that unresolved concentration is acceptable.
2. **Metchie, 2/5:** **4.85/10.03**. Historical offensive snaps/catches and Legette's IR move support possible FLEX involvement. They do not establish a starting receiving role or target increase; Reed/Tremayne remain relevant alternatives. Check the current receiving package and final active list, independently of return duties and Coker's lineup exclusion.
3. **Evans, 2/5:** **2.15/8.01**, salary **$2,000**. Saved retention reason is `above_low_salary_fallback_threshold`, with **no explicit role signal**. Historical receptions support a possible offensive path; narrow survival of strict mean<2 AND P90<8 fallback thresholds does not validate tonight's FLEX value. Check routes versus blocking/special teams; user decision is whether to retain this uncertain cheap receiving path.
4. **Tremble, 1/5:** **2.93/7.57**, salary **$2,400**, outside the $2,000 fallback band. First on the depth chart and past catches support offensive participation, not current target volume. Verify receiving use within the TE rotation; user decides whether that limited evidence supports the saved FLEX exposure.

No automatic exclusions or new floors are proposed. Saved allocated-target values are lagged allocation proxies, not current forecasts. Preserve Coker's preference exclusion; it does not establish that he is out.

## Exact canonical handoff and user actions

Read-only scoped records contain **zero pregame-context runs**, zero current availability rows and saved `availability_row_ids=[]`. The **51-row FanDuel ingest completed with zero unresolved identities**, but it is evidence-only (`injury_csv_consumed=false`). Practice S exists in storage under a league-wide capture labeled `sunday_main`; its season/week/GSIS/team/position matches establish applicability to this verified game. No canonical row exists that merely failed to join.

The genuine [practice-only import JSON](/Users/wones/git/football_26/artifacts/sunday_night_player_evidence_handoff/young-waller-practice-import.json) covers **Young and Waller only**. Both snapshot checksums and GSIS→canonical mappings were verified. It uses the actual `PregameContextRunRequest`/player schema, retains original observation/capture time and provenance, and omits designation, availability probabilities and workload forecasts. Its older observation does not replace the newer Friday review or fill the other nine players' gaps. Underlying practice date/publication time remain unknown. Do not backdate the import receipt.

1. In **Operations → Prepare slate inputs**, verify **2026 / Week 4 / SUNDAY_NIGHT / Showdown**, group **154098**. Open **Load sourced pregame availability evidence (manual JSON)**; paste the JSON into **Sourced pregame evidence JSON**, then click **Load sourced pregame evidence** if choosing to consume these two retained practice facts. For newer sourced facts, preserve their own original timestamps and canonical IDs; do not fabricate clearance for omitted players.
2. **Only after evidence changes**, click **Rebuild slate features and projections**, then **Reload preparation status**. Inspect **Exact persisted source → feature → projection consumption**: expect availability row IDs for the imported players, the new projection ID, and matching per-player context lineage. Nonempty IDs prove consumption, not complete coverage. Rebuilding the unchanged input set cannot fix the gap. Salary/injury reimport and repeated market capture are not required for this handoff.
3. Before lock, check both teams' complete final inactive lists when published, independently verify workload/role updates above, and retain missing facts as missing. No applicable final list was verified during this review; the league inactive-page fetch was inaccessible. Practice, roster placement and active status each answer different questions.
4. Review the existing player and CPT controls without changing defaults. Keep questionable exclusion checked and independent availability assumptions unchanged. After the unresolved decisions, the **user** may click **Run Optimizer**; Showdown automatically verifies/builds dependencies first. No new run or replacement was applied here.

## Bounded saved-lineup review and limitations

| Saved entry | Mean | Individual ceiling sum |
| --- | ---: | ---: |
| 1 | 98.67 | 158.63 |
| **2** | **102.81** | **161.36** |
| 3 | 100.49 | 160.14 |
| 4 | 97.97 | 159.34 |
| 5 | 100.08 | 158.62 |

Lineup 2 leads both measures. Entries 2 and 5 contain Young, Goff, St. Brown, LaPorta, Waller and Metchie, with Young versus Goff captain. Both QBs appear in every entry; these are five correlated entries, not five independent scenarios. Ceiling sums are sums of marginal player P90s, not joint quantiles or win probabilities. This does not establish Lineup 2 as entry-ready or select a replacement.

Role ownership remains unavailable and its selector term disabled uniformly; relative chalk, duplication probabilities and ownership-based value are unsupported. The automatic captain-credibility gate remains **unimplemented**; existing **Exclude from Captain (FLEX still allowed; comma-separated names)** is a user control, not a validated policy. The 95% screen, scoring, priors, exposures, diversity, positions and all preferences remain unchanged; Classic remains parked.

Market observation-age **PASS** applies to the consumed Oct 4 20:54:41Z observation; sportsbook publication freshness remains unknown. Salary publication freshness, weather clearance, current final availability, workload, contest assignment and submission remain unverified. Read-only evidence and preservation hashes are in [the supporting folder](/Users/wones/git/football_26/artifacts/sunday_night_player_evidence_handoff). No application ingest, source capture, rebuild, solve or contest submission was performed.
