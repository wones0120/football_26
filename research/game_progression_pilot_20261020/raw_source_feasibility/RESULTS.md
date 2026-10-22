# One-game raw-source feasibility: partial pass

The raw `2023_06_NO_HOU` source adds **15 source-typed clock-stop observations** absent from the processed game, including **two explicitly labeled two-minute warnings**. It still supplies **no supported physical play-end remaining game clock or restart/enforcement rule**. This is a partial feasibility pass for source clock-stop observations only, not a continuation model or a reason to bulk-download a season.

## Source and bounds

Downloaded exactly one game from the [primary nflverse release](https://github.com/nflverse/nflverse-pbp/releases/tag/raw_pbp_2023), retaining [original RDS bytes](2023_06_NO_HOU.rds). The 40,752-byte asset matches frozen SHA256 `abfdaf9b9a1025a565e76b3ee4365ef7811bc83c5ee80549301c7cb7d2c3fffc`. Acquisition took **1.495 seconds** under a 30-second cap; the compressed cap was 1 MiB. No game-data request was repeated.

The isolated reader setup took 1.939s, using pinned rdata 1.1.0 and xarray 2025.1.2 in a temporary directory. The application environment and repository dependency declarations stayed unchanged. [READER_INSTALL_REPORT.json](READER_INSTALL_REPORT.json) records downloaded wheel hashes. No R code was executed. The serialized payload is 537,165 bytes; the preserved [decoded container representation](CACHED_DECODED.json) is 445,510 bytes, both below the 8 MiB caps.

Two local export assumptions needed correction: a generic JSON exporter rejected a nested dataframe after successful RDS conversion, and an inspection then wrongly assumed the dataframe was the root. Both attempts are preserved in their source/started records. The tested nested-container exporter completed its changed cached inspection in **0.287s**, with no refetch or cap increase. A subsequent native/schema inventory took **0.348s** and assessment of the newly discovered controls took **0.004s**, each under a separate 30-second cached-analysis cap. These were code corrections and distinct evidence assessments, not an unchanged model/source retry. An initial reader-setup syntax error stopped before setup/network activity; it was corrected before the successful setup.

## Native linkage

The decoded object is a dictionary containing nested game metadata and tables. Its play table has **198 rows**. The frozen processed game has **183 rows**, all matched uniquely by native play ID; the raw native game UUID also matches the processed `nfl_api_id`. No display-name joins were used.

All 183 matched IDs agree on native ordering, quarter, type and deletion status. Four administrative rows differ only because their raw clock is blank while the processed source normalizes marker clocks. They remain disclosed rather than silently equated. No processed-only IDs were found.

The 15 additional raw IDs are undeleted typed TIMEOUT rows. Each has a valid regulation event clock and a same-quarter nonincreasing clock bracket between fully agreeing matched native-order anchors. Thirteen report a generic timeout with **unknown cause/team**; two report `Two-Minute Warning`, at Q2 01:58 and Q4 02:00. These are source event observations, not independent official adjudications. No team timeout or budget debit is inferred from them.

[CONTROL_ASSESSMENT.json](CONTROL_ASSESSMENT.json) is the final feasibility disposition. It supersedes the provisional schema-only negative gate in [INVENTORY.json](INVENTORY.json), which was saved before examining the raw-only controls. Its 19 screened records comprise the 15 raw-only controls plus the four shared administrative rows excluded as clock-normalization-disputed anchors; only the 15 controls qualify. Every record remains visible.

## What remains unsupported

- Play `clockTime` matches snap/start clock; `timeOfDay` and nonmissing `endClockTime` remain ISO wall timestamps (164 nonmissing end timestamps, 34 missing).
- `playClock` is zero in all 198 raw rows.
- Drive `gameClockStart`/`gameClockEnd` are drive observations, not physical play-end timestamps for each play.
- The root `gameClock` is a single game snapshot (`00:15`, phase FINAL), not a per-play endpoint history.
- The runoff example remains a narrative annotation: its snap clock is 01:09, the next action is at 00:45, and the UTC times cannot determine how that game-clock interval splits among action duration, enforcement and waiting. No restart signal, enforced runoff duration, clock correction or full terminal-state record is established.

Typed timeout clocks are **not the preceding play's end clock**. Additional controls can improve a separately versioned observation ledger, but their existence does not identify the missing continuation tail or a generated timeout/action policy. Complete original paths, supported law and accuracy remain unchanged. Revised historical source retrieval does not prove original pregame availability.

## Validation and next boundary

**123 tests pass in 0.95 seconds**, including nine new byte-boundary/container/native-link/control cases plus the prior 114 focused cases. They check exact byte caps, decompression amplification, changed hashes, nested dataframe/missing-value export, ambiguous native IDs, clock disagreement, duplicate columns, typed stop bracketing and preservation of unknown play-end/restart/debit fields. [VALIDATION.json](VALIDATION.json) binds final code, source bytes and prior/runtime hashes.

The one-game gate is complete. Do not repeat this download or expand to a season automatically. The supported next implementation could bind these raw-only stop observations in a separate ledger amendment, preserving source IDs and unknown cause/team. Resolving the remaining play-end/restart/enforcement gap requires additional independently specified timing/control evidence; no fit, precision run or live integration is justified by this partial pass. The 15 previously deferred source-state cases remain deferred.
