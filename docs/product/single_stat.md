# NFL Single Stat

Open **Single Stat** in the app navigation. This is separate from Classic and Showdown: exactly three canonical players from the imported contest's native Player Pool, at least two NFL teams, no salary cap or required positions. Every pool row is retained, including quarterbacks and defenders. The default objective is the highest expected requested stat under a descriptive historical baseline. No existing model/default/lineup is changed.

## Source package and workflow

The October 16 user-supplied Week 6 files were verified against official public draft groups: **154977 = DAL–GB Total Yards (44 IDs)** and **154975 = Main Touchdowns (425 IDs across ten games)**. Exact native IDs match both public pools. See [real-pool testing](../../research/single_stat_real_20261016/v1/REVIEW.md). An actual Single Stat pool is required, rather than a Classic/Showdown salary file; the supplied TD template matches Main. The supplied yards template belongs to HOU–JAX Morning and fails an optional compatibility check for DAL–GB; automatic downloads use the saved pool’s own native IDs and are unaffected. Paste or upload this JSON shape through **Import and check readiness**; use the real native CSV's column names, game IDs, source reference and timestamps. This is our evidence package format, not a claimed DraftKings upload format:

```json
{
  "contest_format": "single_stat",
  "variant": "total_yards",
  "game_set_id": "actual-provider-game-set-id",
  "season": 2026,
  "week": 6,
  "source_name": "actual-native-single-stat-pool.csv",
  "source_reference": "actual source file or contest reference",
  "source_observed_at": "2026-10-15T16:00:00Z",
  "scoring_period_end_at": "2026-10-22T03:59:00Z",
  "scoring_period_source": "actual provider scoring-period evidence",
  "contest_status": "active",
  "games": [{
    "game_id": "actual-game-id",
    "teams": ["ACTUAL_HOME", "ACTUAL_AWAY"],
    "original_start_at": "2026-10-18T17:00:00Z",
    "scheduled_start_at": "2026-10-18T17:00:00Z",
    "started_at": null,
    "disabled": false,
    "provider_status": "confirmed",
    "provider_observed_at": "2026-10-15T16:00:00Z",
    "provider_source": "actual DraftKings/provider evidence"
  }],
  "columns": {"source_player_id": "actual ID column", "name": "actual Name column", "team": "actual Team column", "game_id": "actual Game column"},
  "native_csv": "the complete unchanged native CSV text",
  "classification": "native_pool",
  "evaluation_id": "initial"
}
```

Variants are `touchdowns`, `total_yards`, `passing_yards`. `classification=fixture_research` explicitly labels synthetic validation; fixture IDs are not entry IDs. API: `POST /api/single-stat/pools`, `GET /records`, `GET /records/{sha256}`, `POST /optimize` under the same prefix. Optimization takes `pool_sha256`, optionally `allow_partial_touchdown_research` and `allow_incomplete_pool_research` (both false by default).

Native DraftKings IDs resolve through persisted `draftkings` aliases. New native IDs can reuse the existing deterministic team + position + normalized-name identity matcher; successful matches persist a source-ID alias. Names alone never establish identity. Missing IDs remain visible and create an existing unresolved-player queue item and traceable ingest run. Resolve through Operations, then import a separately identified evaluation (`evaluation_id` changed) to obtain a new frozen assessment. Retrying an identical package returns its original record. Original raw CSV, source hash, prior identity/stat assessments and reports remain immutable under `artifacts/single_stat_ledger`; records include canonical IDs and source IDs. No database schema change is needed.

Native UTF-8 BOM and CRLF files stay unchanged in evidence. Set `columns.game_id` to `Game Info` and provide `native_game_ids` mapping each exact native Game Info string to its verified provider competition ID. Optional `player_evidence` records contain each native player ID’s provider `status`, `disabled`, `source_reference`, `observed_at`; `source_file_observed_at` preserves the original file clock separately. Native/provider OUT, IR, doubtful and disabled players retain forecasts but are excluded from research selection; questionable players retain their designation and unchanged descriptive baseline, without assuming full workload. Captured status and measured-subset scope are visible in reports.

Choose a saved pool, inspect readiness, and click **Generate highest expected stat lineup**. Reopen the immutable report from **Saved pools and reports**. All report data including stat components/provenance is available in the expandable evidence section. Open **Automatic native-pool research CSV** on any saved report. The default download requires no per-slate template: the service reopens that report’s original immutable imported CSV, validates its source hash and column mapping, proves each canonical-to-native ID/team/game binding, and writes exactly:

```csv
FLEX,FLEX,FLEX
<saved native ID 1>,<saved native ID 2>,<saved native ID 3>
```

The same mode/stat/Game Set/pool, three distinct canonical/native players, two teams, Single Stat FLEX roles where present and current known lock/availability rules must match. Non-numeric, missing, duplicate, ambiguous or foreign-pool IDs block downloads. Legacy saved reports work when their original native evidence still proves these bindings; their historical disabled-export fields and forecast assessments remain immutable. Missing original native evidence requires a fresh supported import, not an ID guess.

The three positional FLEX headers come from the supplied official templates. Instructions explicitly put a player ID or Name + ID beneath each slot; instruction/reference columns are lookup material rather than lineup slots. The automatic file emits the minimal roster portion with native IDs from the one imported pool, CRLF and standard CSV serialization. This matches the observed roster layout; **actual DraftKings acceptance has not been tested by uploading or submitting**. The official [CSV guidance](https://support.draftkings.com/dk/en-us/how-do-i-upload-or-edit-multiple-lineups-at-once?id=kb_article_view&sysparm_article=KB0010800) limits each file to one pool/slate and 500 lineups, requires slate-specific IDs below each position and prohibits adding locked players. It also distinguishes lineup upload from entry assignment. Our single-lineup output follows those constraints; no contest/entry ID or assignment is created.

Use **Download lineup CSV** directly once native identity, format and lock checks pass; no acknowledgment checkbox is required. CSV download does not change `entry_ready=false`, repair missing history/rare TD forecasts or perform a submission. Immutable receipts preserve report/pool/content hashes, exact bytes, native IDs, schema version and `automatic_from_native_pool=true`; template references are null for this default. The filename includes `research`.

**Optional template compatibility check** still validates a supplied native template without making it a prerequisite for ordinary downloads. A legacy API request that explicitly supplies a matching `template_sha256` preserves that complete template’s metadata; a contradictory template is rejected. The older HOU–JAX template mismatch no longer blocks the DAL–GB automatic native-pool CSV, and no HOU–JAX lookup rows are copied into it. APIs remain `POST /api/single-stat/templates`, `GET /records/{report_sha256}/export-readiness`, and `GET /records/{report_sha256}/download` (optional `template_sha256` only for the legacy full-template path).

See [automatic download verification](../../research/automatic_native_downloads_20261016/v1/REVIEW.md) for actual Single Stat and Tiers files and checks.


## Scoring and forecast coverage

| Variant | Metric and unit |
| --- | --- |
| Touchdowns | Count of rushing, receiving, kick-return, missed-field-goal-return, punt-return, offensive-fumble-recovery and defensive touchdowns. Passing TDs contribute nothing. |
| Total Yards | Rushing + receiving yards. Passing yards contribute nothing. |
| Passing Yards | Passing yards only. |

Scoring returns **unknown** when any required category is missing, including rare touchdown types. Explicit provider-disabled games score zero. Forecasting uses each canonical player's last three distinct observed games strictly before the requested season/week and observed before the pool source cutoff. It preserves raw row IDs, source-system/native IDs, ingest IDs, observed clocks and numeric components. Reimports of the same historical game do not duplicate samples. Late-ingested statistics cannot be treated as available for an earlier cutoff. There is no fantasy-point conversion, trained stat-head claim, opponent/current-workload/injury adjustment, calibrated interval or contest-win probability.

Read-only audit of the current data found `nflreadpy` weekly passing/rushing/receiving yards and rushing/receiving TDs. Aggregate `special_teams_tds`, `def_tds`, `fumble_recovery_tds` fields exist, but this version does not assume that aggregate names prove every exact requested return/recovery subtype without a verified mapping. Those exact TD categories remain unknown. **Allow explicitly partial touchdown research** maximizes only measured components and labels the objective `highest_expected_covered_touchdowns`; this does not claim a complete touchdown forecast. A complete pool ranking also blocks when any player's identity or requested history is unavailable. **Allow research among measured players only** explicitly permits a subset comparison, saves every excluded player/reason and labels `INCOMPLETE_POOL_RESEARCH`; the full-pool optimum remains unknown. These options never alter source facts.

## Locks and provider decisions

A newly generated lineup cannot add a locked player. Lock uses the scheduled team kickoff, an earlier observed real start, or the original kickoff for disabled games. The app checks exact Game Set membership and teams, provider status, contest status and scoring-period closure. Unknown or pending provider decisions block generation. Saved reports are immutable observations, not editable entries; reopening does not grant permission to swap locked slots.

The supplied detailed rules describe less-than-24-hour changes, the first Wednesday 11:59pm Eastern cutoff, discretionary changes more than 24 hours before start, zero/one-active-game cancellation exceptions and suspension settlement. This slice preserves explicit provider decisions and the sourced scoring-period end; it does not infer cancellation or refunds from a game count, invent a provider decision, or calculate a speculative revised scoring period. Refresh authoritative pool/status evidence after changes. No report asserts entry readiness.

## Actual-result accounting

`POST /api/single-stat/actual-results` takes `report_sha256`, `source_reference`, timezone-aware `source_observed_at`, exactly three canonical `players` with `stats`, optional `disabled_game_ids`, and explicit true attestations: `official_nfl_statistics`, `original_scoring_period_only`, `suspended_game_resumption_stats_excluded`. Disabled-game IDs must belong to the saved Game Set. The saved report exposes **Record official actual stat evidence** for this package; actual results can then be reopened from the same library. The separate immutable result preserves original forecasts and source attestations. Native actual evidence cannot predate the game start; synthetic results carry `FIXTURE_ACTUALS`. All seven TD subcategories must be supplied for a complete result; missing categories produce `INCOMPLETE_ACTUALS`, never implicit zeros. Actuals must exclude later resumed-game stats per the supplied rules. This source-attested accounting does not independently adjudicate official settlement.

## Rule provenance

The exact user-provided detailed NFL rules are preserved in the validation research folder. On 2026-10-15 the current official [DraftKings Single Stat overview](https://support.draftkings.com/dk/en-us/game-style-single-stat?id=kb_article_view&sysparm_article=KB0010273) independently confirmed selecting three athletes without salary-cap limits. The overview is general; the complete current NFL-specific detailed text was not independently retrieved. Saved records state that distinction and retain the user-supplied version. Source clocks, app capture clocks and sports season/week are separate; no clock discrepancy is silently normalized.

Single Stat and Tiers: **Download lineup CSV** is available as soon as native identity, roster, format and lock checks pass, without a download acknowledgment checkbox. Coverage limitations remain visible; downloads do not submit entries.

CSV download errors now appear in the workspace instead of saving an API JSON error as a file. Successful responses are checked for CSV content and the correct roster headers before a `.csv` download is started.
