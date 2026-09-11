# Prospective Source Capture

Last validated: 2026-09-07

Contract: `prospective_source_snapshot_v1`

Migration: `0019_prospective_source_snapshots.sql`

## Outcome

The repository has preserved current full-season 2026 schedule and Week 1 weekly-roster observations
plus the first real DraftKings Week 1 `SUNDAY_MAIN` salary observation before their games: 272
regular-season games with 272 unique canonical game IDs, 2,902 roster rows across all 32 teams, and
719 salary rows covering all 12 Sunday Main games. The roster ingest resolved 2,901 source
identities and retained its single ID-less row in the review queue. DATA-002 itself remains
incomplete until the other approved pre-lock observations are retained.

The capture path supports:

- a manually downloaded DraftKings salary CSV, ingested only from its preserved copy;
- nflreadpy schedules, weekly rosters, injuries, and snap counts serialized as observed CSV
  snapshots, with weekly rosters ingested from the preserved bytes;
- repeated polling without duplicate files or ingest runs;
- cutoff selection that excludes an observation made after slate lock.

## Evidence Contract

Each `source_snapshot` row and adjacent `manifest.json` records:

- source system, dataset, season, week, and slate;
- server receipt time (`observed_at`) and capture time (`captured_at`);
- source/effective time when supplied; otherwise `effective_at` equals the observed time;
- slate lock time and whether the observation preceded it;
- SHA-256, byte count, row count, media type, and immutable artifact path;
- source URI, source-license statement, observation basis, and source-specific metadata.

The snapshot ID is deterministic for source, dataset, slate scope, and content hash. Identical
content in the same scope reuses the original observation; changed content appends a new version.
PostgreSQL has a trigger that rejects `UPDATE` and `DELETE` on `source_snapshot`. The separate
append-only `source_snapshot_ingest_run` table links preserved evidence to downstream ingest runs
without mutating the snapshot.

## Weekly Command

For safe directory polling, rename the DraftKings download with its season and zero-padded week:

```text
DKSalaries_2026_01_sunday_main.csv
```

Then run before the first game in the slate:

```bash
python scripts/capture_prospective_sources.py \
  --season 2026 \
  --week 1 \
  --slate sunday_main \
  --slate-lock-at 2026-09-13T13:00:00-04:00 \
  --draftkings-directory ~/Downloads \
  --nflreadpy-datasets schedules weekly_rosters injuries snap_counts
```

Use `--draftkings-path ~/Downloads/DKSalaries.csv` when retaining DraftKings' generic filename.
Directory discovery deliberately ignores that generic name because a scheduled run cannot prove
which week an old generic file belongs to.

`SOURCE_SNAPSHOT_ROOT` defaults to `artifacts/source_snapshots`, which is excluded from Git. Set it
to an absolute path on backed-up durable local or mounted storage before the first live salary
capture. Repository-local ignored files are not a backup. The command prints the absolute
artifact/manifest paths, checksum, observation time, pre-lock decision, row counts, and ingest
result as JSON. A nonzero exit means one or more requested sources failed or a salary observation
arrived after lock.

## UI Schedule Ingest

In `Research Lab` > `Ingestion`, select the season and choose `Load Schedules`. The API fetches the
nflreadpy schedule once, preserves the full selected season or week slice as an immutable CSV, then
reads that captured artifact into `raw_nfl_schedule`. The ingest run stores the artifact path and
checksum and receives a deterministic ID derived from the snapshot; `source_snapshot_ingest_run`
links both records. An unchanged repeat reuses the verified snapshot and completed ingest run.

This route intentionally has no slate lock because the NFL schedule is season-level fixture data,
not a DFS salary observation. Any later upstream schedule change creates a new content-addressed
snapshot and ingest run before replacing the selected database rows.

## DraftKings Ingest Safety

The command captures the source bytes first. Only a snapshot with `observed_at <= slate_lock_at`
can enter salary ingestion. The ingest service receives the read-only captured file path, and its
existing checksum must equal the snapshot checksum. Canonical matching and unresolved-queue rules
remain unchanged. The ingest run ID is derived from the snapshot ID, so retrying the same capture
returns the same completed run.

A post-lock download remains valuable audit evidence, so it is retained. It is intentionally not
linked to an ingest run and is absent from `eligible_snapshots(cutoff_at=...)` for that lock.

## Real Week 1 Salary Capture

The source-authorized `DKSalaries_2026_1_SUNDAY_MAIN.csv` file was captured on 2026-08-28 at
`07:37:56.614169-04:00`, before the declared 2026-09-13 `13:00:00-04:00` slate lock.

| Check | Result |
| --- | --- |
| Snapshot ID | `d893bd08-475f-50b2-8b29-235670d3805d` |
| SHA-256 | `39f7d4669ba4d45c711ae8b135468ce01180c5b181d1f77076c75258a72287a6` |
| Ingest run ID | `ab38816d-9b5d-5f7e-8f24-ca60ee1d3f8d` |
| Raw / curated rows | 719 / 719 |
| Canonical games | 12 |
| Resolved / unresolved player identities | 531 / 188 |
| Unresolved DST identities | 0 |
| Artifact verification | Passed at the configured durable snapshot root outside the repository |
| Identical rerun | Reused the same snapshot and completed ingest run; no duplicate artifact or rows |

The initial 188 unresolved player rows entered the explicit review queue; none were silently
dropped or joined by display name alone. Those identities must be resolved or accepted under the
governed quarantine rules before the full salary pool can enter projections or optimization.

After the September 3 weekly-roster ingest, 139 salary identities gained deterministic
name+team+position matches and were resolved through the normal alias workflow. Coverage is now
670/719; 49 salary rows remain unresolved and the August 28 salary export remains stale. A fresh
salary download is still required before projection or optimization readiness can pass.

## Real Week 1 Weekly-Roster Capture

The canonical 2026 weekly-roster release was captured on 2026-09-03 at
`15:04:53.692296-04:00`, before the declared Sunday Main lock.

| Check | Result |
| --- | --- |
| Snapshot ID | `3cf54819-2ebd-569e-a8ce-b487d17c2786` |
| SHA-256 | `0c4994316d2efa8dc0db12a719628ea744267d0f75c0fa6f4bbded62d04dab29` |
| Ingest run ID | `988b4f3f-872b-5e43-8c13-bda661836b26` |
| Raw / identity-resolved rows | 2,902 / 2,901 |
| Teams / active-status rows | 32 / 1,695 |
| Open roster identities | 1 (`Al-Jay Henderson`, no native source ID) |
| Capture path | Canonical nflverse release CSV fallback from nflreadpy 0.1.5 season validation |
| Artifact verification | Passed at the configured durable snapshot root outside the repository |

The full-season schedule was also refreshed from changed upstream content at
`15:09:33.340377-04:00`: snapshot `297eff9c-1cb6-5ccb-b7df-238db0d30923`, checksum
`fd8231a753121592197f776c9f564be6444d41e742e029622eab34e317e9ff55`, and 272/272 completed
raw/curated rows.

## Real Week 1 Wednesday Night Showdown Capture

`DKSalaries_2026_1_WEDNESDAY_NIGHT.csv` was captured on 2026-09-03 at
`16:24:17.535132-04:00`, before the NE at SEA lock on 2026-09-09 at `20:20:00-04:00`.

| Check | Result |
| --- | --- |
| Canonical game | `2026_01_NE_SEA` |
| Snapshot ID | `f5a910c0-3ed6-5b3c-b94d-9e1891da4b37` |
| SHA-256 | `9f7f2016d609e5f96d772d43a03205222799f4342e7f67338c237be109c8757e` |
| Ingest run ID | `f29795fa-4b48-5fd6-888c-2e2f73b5f977` |
| Raw / curated rows | 136 / 136 |
| Logical players / teams | 68 / 2 |
| Initial / post-roster identity rows | 98 / 128 of 136 slot rows |
| Playable active pool | 37 players: 35 `ACT` plus 2 team defenses |
| Excluded by roster status | 6 `CUT`, 9 `DEV`, 8 `RES`, 8 roster-missing |
| Playable identity coverage | 37 / 37 |
| FLEX/CPT site-ID coverage | 37 / 37 for both roles |
| Playable positions | 6 QB, 8 RB, 11 WR, 8 TE, 2 K, 2 DST |
| Minimum retained salary | $200 |

Thirty initially unresolved CPT/FLEX rows were resolved through the governed alias workflow only
after exact name, team, position, and native weekly-roster identity agreement. Eight rows for four
roster-missing players remain queued. They do not enter the playable pool. Showdown cash and GPP
remain blocked on a projection run, positive projection coverage, and offensive-position
projections; the missing injury snapshot remains a warning.

The changed September 7 download was captured as a second immutable version and replaced only the
active curated salary slice. Snapshot `b61f0287-177f-5993-98e8-7d216cf5e335` has SHA-256
`24dea66c2d7d1b479454db910e8cc8da93ac76cf5df82897c03fe15119072356`; ingest
`597fa402-3878-5d31-aee8-cf79193b38ca` completed with 136 raw and 136 curated rows. The salary
status repair preserves 15 `OUT` and 6 `IR` logical players. All six unresolved slot rows belong
to three `OUT` players and are therefore excluded before projection identity coverage is measured.
Projection run `d8bcafe3-6ed3-4cd4-a363-efd6216e807a` wrote 35 supported-position rows and stores
the exact 21-player/42-slot salary-status exclusions plus 10-player/20-slot roster exclusions.
Two kickers are separately reported as unsupported by the current point model. Charbonnet,
Boutte, and every `DEV`/roster-missing skill player are absent; Price, Holani, and Smith-Njigba are
present. Readiness now reports 37/37 eligible playable identities; the missing injury snapshot and
ownership remain warnings for Showdown GPP.

## nflreadpy Boundaries

The command normally captures exactly the tabular frame returned by the installed nflreadpy version
after season/week filtering and records that package version. If `weekly_rosters` rejects a season
that is exactly one year beyond its reported maximum, the adapter reads the canonical
`nflverse-data` weekly-roster release CSV directly. Other errors and larger season gaps still fail.
The source URI, rejected loader message, package version, and fallback mode remain in snapshot
metadata. The UI schedule and weekly-roster actions ingest from captured bytes and record the
snapshot-to-run link. Existing snap ingestion and canonical identity rules remain the Silver/Gold
path; this change does not treat current injury or schedule values as historical pre-lock evidence.

The default license strings are provenance reminders, not a grant of rights. Replace them with an
approved source-specific statement when required. Paid or separately licensed sources should use
the same capture service only after their terms and allowed storage/use are recorded.

## Verification And Recovery

Focused tests prove:

1. capture files and manifests are content-addressed and idempotent;
2. modifying the original download does not alter preserved evidence;
3. DraftKings ingestion uses the preserved checksum and resolves canonical identity normally;
4. a post-lock salary capture creates no ingest run and is excluded by cutoff selection;
5. nflreadpy frames are week-filtered and retain loader-version lineage;
6. UI schedule loads ingest from the captured artifact, record its checksum and lineage link, and
   reuse an unchanged completed run;
7. a one-season-behind weekly-roster client uses the canonical release fallback, while the captured
   roster is ingested exactly once with checksum and snapshot/run lineage;
8. freshness lookup treats slate keys case-insensitively.

`verify_snapshot_artifact` re-hashes an artifact and validates its manifest. A missing or mismatched
artifact is an integrity failure; the service will not silently reconstruct or overwrite it.

The salary reload/status repair passes its 74 focused tests. The full backend suite passes 470
tests, all 13 UI tests pass, and the production UI build succeeds.
