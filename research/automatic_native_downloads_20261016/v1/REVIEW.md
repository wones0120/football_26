# Automatic native-pool downloads — Single Stat and Tiers

**All three requested outputs were downloaded in the actual Chrome localhost app and parsed against their saved lineups. A separate template is no longer required for each slate.**

| Output | Automatic roster header | Exact downloaded native IDs | CSV |
| --- | --- | --- | --- |
| Main Single Stat TD | `FLEX,FLEX,FLEX` | `44488638,44488571,44488577` | [TD CSV](touchdowns_automatic_browser.csv) |
| DAL–GB Single Stat Total Yards | `FLEX,FLEX,FLEX` | `44533425,44533428,44533427` | [Total Yards CSV](total_yards_automatic_browser.csv) |
| Main Tiers | `T1,T2,T3,T4,T5,T6` | `44498892,44498898,44498900,44498906,44498917,44498921` | [Tiers CSV](tiers_automatic_browser.csv) |

The Single Stat trios remain Brian Robinson Jr./Kenneth Walker III/James Cook III and CeeDee Lamb/George Pickens/Christian Watson. The Tiers file preserves the saved one-player-per-tier order. [Browser verification](browser_verification.json) records original download paths, hashes, headers, IDs and source report/pool hashes. The earlier TD full-template file remains untouched; Chrome saved the automatic TD file with a `(1)` filename suffix.

## Workflow

Open a saved Single Stat or Tiers report, read the displayed limitations, accept research download consent and download. The application derives the slot layout from the supported format and exact native IDs from its imported immutable salary/player pool. It does not ask for a new per-slate template. Existing saved reports work when their original native source evidence still proves the roster. The imported HOU–JAX yards template cannot contaminate the DAL–GB output: that output now comes directly from its own 44-player native pool, not any template reference table.

Single Stat shows **Automatic native-pool research CSV** with **Optional template compatibility check**. The old full-template API remains available for explicit matching-template requests. A bad optional template is still rejected; it does not become a prerequisite for the ordinary automatic path. Readiness and download APIs validate again at request time; an enabled UI link does not bypass a subsequent lock or source failure.

## CSV evidence and practical limit

The exact supplied official templates establish three positional FLEX headers for Single Stat and ordered T1–T6 headers for this Tiers slate. Their instructions put numeric player IDs or Name + ID beneath the appropriate roster slots; instruction/reference columns sit outside those slots. The automatic output emits only the supported roster header and native-ID rows using deterministic UTF-8/CRLF CSV serialization. [Schema evidence](schema_evidence.json) preserves observed headers, instructions, original template paths and hashes. Reference rows from another slate, contest IDs and entry-assignment columns are never copied.

The current [official DraftKings CSV guidance](https://support.draftkings.com/dk/en-us/how-do-i-upload-or-edit-multiple-lineups-at-once?id=kb_article_view&sysparm_article=KB0010800) requires one slate/pool per file, a maximum of 500 lineups, exact slate-specific player IDs below the relevant position and no additions after game lock. It also distinguishes lineup upload from assigning a lineup to a contest entry. The automatic output follows the observed roster layout and these constraints. **Actual DraftKings parser acceptance has not been tested by uploading or submitting.** No account, contest submission, purchase or entry assignment was accessed.

## Validation and preserved meaning

- Each saved canonical player must map to its exact native ID in the same imported mode/stat/slate/Game Set/pool. Foreign IDs, missing/ambiguous identity evidence, duplicate IDs, wrong roles, invalid tier order and illegal rosters block download.
- Single Stat independently reopens and verifies the original immutable native CSV hash, positional column mapping, native team/game identity and supported FLEX role where present. All three canonical/native IDs must be distinct and represent at least two teams.
- Tiers validates all source tier memberships and renders one selected native ID in each source tier’s order; its dedicated [verification](../../tiers_2026w6_20261016/v3/browser_download_verification.json) confirms the exact six saved players and receipt hash.
- The common serializer preserves repeated FLEX headers positionally, rejects malformed/incomplete/duplicate/non-numeric IDs, enforces roster cardinality and safely serializes CSV cells. No dictionary collapses repeated headers.
- Current known lock/availability decisions and explicit research consent remain mandatory. Old saved report metadata is not rewritten, and an old disabled-template field is not treated as the current automatic-export gate.
- `entry_ready=false`, missing-history and rare TD/scoring limitations remain intact. Receipts identify the CSV schema and source hashes and preserve `assignment_created=false` and `submission_confirmed=false`. Automatic output does not renew source clocks or promote a research lineup to a complete projection or entry-cleared recommendation.

The final combined Single Stat/shared/Classic-export/Tiers regression suite passed **74 tests**; Tiers UI checks passed **2 tests**. UI TypeScript/Vite build passed with only the existing chunk-size warning. The final idle API and durable-worker restart was coordinated with both active agents; activated endpoints exactly matched all browser-downloaded bytes, including the refreshed-status Tiers report. models, projections, Classic/Showdown settings and existing lineups remain unchanged.

[Single Stat automatic download screenshot](total_yards_automatic.png) · [Tiers detailed workflow and review](../../tiers_2026w6_20261016/v3/REVIEW.md)
