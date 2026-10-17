# Single Stat native template downloads

**Main TD research CSV is ready for review and was downloaded through the actual Chrome localhost app. DAL–GB yards export is correctly blocked because the supplied yards template belongs to HOU–JAX.**

## Original files and exact format

Originals were found under `/Users/wones/NFL` and were not edited. Byte-preserving snapshots are retained here:

| Original | SHA-256 | Native reference pool |
| --- | --- | --- |
| `draftkings_single_stat_template_tds.csv` | `3a03390b08b28c6d877ef5dafd41d6335df2716731170b86f1cf8f0be9d3142b` | Main TD, 425 players; exact match to saved pool |
| `draftkings_single_stat_template_yards.csv` | `10417e3a5f02f0b6a6e1c6523940adb728f9fdc2bf22f220c671734efc3a50b2` | **HOU @ JAX, October 18 9:30am ET**, 42 players; does **not** match DAL @ GB, 44 players |

Both begin with the exact CSV header `FLEX,FLEX,FLEX,,Instructions`. An instruction block says to copy native IDs into each roster position and allows up to 500 lineups. Below it is an eight-field player reference table offset by four empty cells. There are no contest IDs, entry IDs or assignment fields. The implementation exports one saved three-player lineup, fills only the first blank lineup row’s first three cells, and preserves every other template cell. Original template text/hash remain immutable; CSV output uses CRLF line endings.

Duplicate FLEX headers are treated positionally, not through a dictionary. Changed slot counts, existing roster values, unexpected assignment columns, multiple embedded headers, duplicate native IDs, nonnumeric IDs and contradictory native game/team evidence are rejected. Matching a trio alone is insufficient: the **entire** native template pool must match the saved pool.

## Verified TD output

Saved report **5ceb973d1643** exports precisely:

| FLEX | Native ID | Team |
| --- | --- | --- |
| Brian Robinson Jr. | 44488638 | ATL |
| Kenneth Walker III | 44488571 | KC |
| James Cook III | 44488577 | BUF |

Three distinct canonical players, three distinct native IDs, at least two teams, exact source membership and current known locks were checked. No salary cap or position requirement is introduced.

[Browser-downloaded CSV](touchdowns_browser_download.csv) · [API-verified CSV](touchdowns_verified_download.csv)

Both byte sequences match exactly: SHA-256 **`ed6c68a6de5f23e5746e63312818616c5ae9a269f8d076985f17ba22e52a2ef7`**. Parsing the browser download confirmed the three IDs and all three FLEX headers; resetting the filled cells yields the original template’s entire CSV cell matrix. Chrome also saved the file to `/Users/wones/Downloads/single-stat-touchdowns-research-5ceb973d1643.csv`.

The UI exposes **Template-verified research CSV**, **Verify native upload template**, the explicit research acceptance checkbox and **Download research lineup CSV**. Consent is required before the link appears and by the API. Current source reports retain `INCOMPLETE_POOL_RESEARCH` and `entry_ready=false`; their unknown rare TD categories/history are not repaired by a valid template. The receipt preserves report/pool/template/content hashes, native IDs, exact bytes, original forecast coverage, `entry_ready=false`, `submission_confirmed=false`, `assignment_created=false`. Downloading creates no contest assignment and submits nothing.

## Yards blocker

API and Chrome rejected the supplied yards template with this exact reason:

> Template belongs to a different native pool: 42 template IDs, 44 saved pool IDs; template games: HOU@JAX 10/18/2026 09:30AM ET. Supply the exact template for this saved pool; IDs cannot be substituted.

The DAL–GB report remains intact at 292.333 descriptive baseline yards. Its players/IDs cannot be inserted into a HOU–JAX template. **The matching DAL–GB Total Yards upload template is the remaining input needed to download that saved trio.** General Total Yards export behavior passes a matching-template regression test; no artificial IDs or rewritten Game Set were used to force the supplied file through.

## Checks and runtime

- Targeted Single Stat/template tests pass, including round-trip export for both supported categories, duplicate headers, wrong pool/game/format, nonblank assignment prevention, explicit consent, locks, immutable receipt bytes and API response headers.
- UI TypeScript/Vite build passes; existing chunk-size warning remains.
- The real localhost API was reloaded once after both active feature agents released it. Models, live projection defaults, Classic/Showdown settings and existing lineups remain unchanged. Tiers work was coordinated separately and its shared-file changes were preserved.
- Chrome localhost imported/verified the TD binding, downloaded the actual file and displayed the research limitation controls. The mismatched yards template was pasted unchanged and visibly rejected. No DraftKings account, authenticated site, contest upload, submission or purchase was accessed.

[TD download UI](td_download_ready.png) · [Wrong-game yards rejection](yards_template_rejected.png) · [Source binding/API validation](verification.json) · [Browser bytes verification](browser_download_verification.json)
