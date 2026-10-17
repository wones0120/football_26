# Real Single Stat pool testing — 2026 Week 6

Both exact files from `/Users/wones/NFL` are imported into the real local app. Their byte-preserving snapshots, hashes and exact source/provider capture clocks are retained alongside the source evidence. No originals were edited. A separately identified clock-corrected evaluation preserves the initial imports rather than replacing them.

| File | Official verified category / draft group | Exact player IDs | Game Set |
| --- | --- | --- | --- |
| `DKSalaries_2026_6_SUNDAY_NIGHT_SINGLE_STAT_YARDS.csv` | **Total Yards**, DG **154977** | 44/44 | **DAL @ GB**, Oct 18 8:20pm Eastern (Oct 19 00:20 UTC) |
| `DKSalaries_2026_6_SUNDAY_MAIN_SINGLE_STAT_TDS.csv` | **Touchdowns**, DG **154975** | 425/425 | Ten Oct 18 games, 1pm–4:25pm Eastern |

Category is confirmed by the [official public NFL lobby](https://www.draftkings.com/lobby/getcontests?sport=NFL), then every native ID is matched to official public draftables ([Total Yards](https://api.draftkings.com/draftgroups/v1/draftgroups/154977/draftables), [Touchdowns](https://api.draftkings.com/draftgroups/v1/draftgroups/154975/draftables)). The generic “YARDS” filename was not the category authority. Scope details and public source captures are in [verified_scope.json](verified_scope.json).

Main games are CHI–ATL, BAL–CLE, TEN–IND, CAR–PHI, NO–NYG, NYJ–NE, PIT–TB, ARI–LAR, BUF–LV and LAC–KC. Both supplied pools have RB/WR/TE rows only, FLEX roster labels, no QB/defender rows and no Salary column. This is native membership, not an imposed position restriction. All **469 identities resolved**, using deterministic team/position/name source evidence for new native IDs and persisting the resulting DraftKings aliases. No name-only join, ID substitution or player drop occurred.

## Saved Total Yards comparison

Report **c5e8182c2a6e** maximizes the measured eligible subset:

| Player | Team | Native ID | Last-three rushing + receiving yards mean |
| --- | --- | --- | ---: |
| CeeDee Lamb | DAL | 44533425 | 101.333 |
| George Pickens | DAL | 44533428 | 95.667 |
| Christian Watson | GB | 44533427 | 95.333 |
| **Total** | **2 teams** | **3 distinct canonical players** | **292.333 yards** |

These are the three largest available eligible means, and already satisfy the two-team rule. No passing yards or fantasy-point conversion contributes. Lamb’s sampled totals are 112, 183 and 9 yards; Pickens 82, 75 and 130; Watson 96, 47 and 143. All are stored observed 2026 weeks 3–5, with raw-row/ingest/native/canonical identifiers and observation clocks in the saved report.

Legal alternatives, evaluated descriptively from the same frozen pool rather than as a portfolio or win-probability model:

- Lamb + Pickens + Matthew Golden: **280.333**, −12.000 yards.
- Lamb + Watson + Golden: **280.000**, −12.333.
- Lamb + Watson + Javonte Williams: **279.333**, −13.000.

44 native rows remain visible; 36 have any measured history, eight have none. Nine native OUT/IR rows are excluded; overlapping missing-history exclusions leave **29 research-eligible players**, with **15 distinct exclusions**. Jacobs and Musgrave remain assessed but cannot be selected because OUT. Baselines for older/limited histories are not current usage forecasts.

## Saved Touchdowns comparison

Report **5ceb973d1643** uses explicit partial-category and incomplete-pool research opt-ins:

| Player | Team | Native ID | Last-three rushing + receiving TD mean |
| --- | --- | --- | ---: |
| Brian Robinson Jr. | ATL | 44488638 | 1.333 |
| Kenneth Walker III | KC | 44488571 | 1.333 |
| James Cook III | BUF | 44488577 | 1.333 |
| **Total** | **3 teams** | **3 distinct canonical players** | **4.000 covered TD** |

**This trio is not uniquely superior.** Bijan Robinson and Derrick Henry also have means of 1.333; five players are tied at the top. The saved exact optimizer’s canonical-ID tie-break selects one equal-scoring trio, not a football judgment. Bijan + Henry + Walker, Bijan + Henry + Cook, and Henry + Walker + Cook are legal alternatives at the same **4.000** measured TD mean. Two Atlanta backs can legally coexist; correlation and current goal-line roles are not modeled by this simple objective.

The objective is `highest_expected_covered_touchdowns`: rushing + receiving TD only in available histories. Passing TD never counts. Kick returns, missed-FG returns, punt returns, offensive fumble recovery and defensive TD forecast components remain **unknown**, rather than zero. Exact actual-result scoring supports all seven qualifying TD categories separately. Aggregate return/defense/recovery data is not silently treated as subtype-complete coverage.

425 native rows remain visible; 357 have measured history, 68 have none. Captured OUT/IR/doubtful status excludes **74** rows; overlaps leave **302 research-eligible players**, **123 distinct exclusions**. Questionable players retain their designation and unadjusted measured baseline; these reports do not certify workload or game-day availability. Hurts is absent from both native pools (no QBs), so his OUT status cannot affect these three-player selections.

## Data and evidence limits

The baselines use the last three distinct observed games available before the request cutoff and requested week, never fantasy projections or future-week results. Current public native status was refreshed in the captured draftables. No opponent, QB change, goal-line workload, injury redistribution, weather, ownership, calibrated uncertainty or contest-win probability adjustment is applied. This is the first real-pool workflow test, not validation that last-three means outperform other forecasts.

A bounded selected-TD sanity audit used source rushing/receiving TD columns rather than the previously flagged DST fantasy labels. Four of nine historical observations passed the available individual-TD/team-points bound; five lacked game-score corroboration in the selected schedule evidence. No impossible bound was detected, but missing corroboration remains explicit in [selected_td_source_sanity.json](selected_td_source_sanity.json); this is not a full official outcome reconciliation. The older DST label issue is not reused as TD truth.

The known seven-category TD model gap and missing histories mean both saved reports are **INCOMPLETE_POOL_RESEARCH**, `entry_ready=false`. Full-pool default optimization correctly blocks. The requested three-player/two-team legality, source membership, locks and unavailable exclusions still apply to every research trio. There is no salary constraint. The provider Game Sets were Pre-Game with no exceptional schedule messages at capture; the source-stated Wednesday 11:59pm Eastern scoring-period rule is retained without inventing a provider adjustment.

## Validation and operational state

- **41 backend tests passed**: 23 Single Stat cases including the new real-schema BOM/Game Info/status and canonical alias tests, plus 18 existing DraftKings-export tests.
- UI TypeScript/Vite build passed; existing bundle-size warning only.
- Actual Chrome localhost app imported the same exact packages idempotently through its text input, generated both reports, reloaded the app and reopened each original saved hash. Native status, objective, metric units and incomplete coverage were visible. File-chooser upload was unavailable because Chrome extension file-URL access is disabled; package paste worked without changing extension permissions.
- One coordinated API reload occurred after Morning and Entry History agents confirmed idle, activating both features; no job was interrupted. API remains running. Existing Classic/Showdown slate/settings/run selections remain unchanged (the shell still shows the user’s Morning context, while Single Stat source scope is independent and visible).
- No DraftKings login, submission, purchase or entry file export occurred. Native salary/pool CSVs are not upload templates; CSV export remains disabled.

[Reopened Total Yards screenshot](total_yards_reopened.png) · [Reopened Touchdowns screenshot](touchdowns_reopened.png) · [Full bounded comparison](comparison.json) · [Source hashes and pool receipts](manifest.json)
